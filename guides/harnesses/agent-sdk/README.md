# Agent SDK Harness Guide

Playbook for an agentic project that uses Anthropic's [Claude Agent SDK for Python](https://github.com/anthropics/claude-agent-sdk-python) as the harness, hosted inside the project's own application.

## When to choose this harness

Pick `agent-sdk` when:

- The end product is an application end users interact with through a UI (chat or task), not a CLI session.
- You want Anthropic to maintain the agent loop, tool dispatch, session management, and subagent topology rather than building it yourself.
- You're comfortable on the Python server stack in `guides/server/README.md`.

If your product is artifacts authored by Claude Code with no end-user-facing application, use `claude-code` instead. If the SDK's loop doesn't fit your control needs, use `claude-api` instead.

## Assumed constraints

This guide commits to a specific shape:

- **Server runtime** — Python in-process inside FastAPI, per `guides/server/README.md`. The SDK is invoked from request handlers; same uvicorn worker handles HTTP and the SDK.
- **Streaming** — Server-Sent Events from the server to the client.
- **Persistence** — every session, message, tool call, and run is persisted to Postgres so runs can be evaluated and audited after the fact.
- **Multi-user** — sessions are scoped per `current_user`, resolved by an auth dependency that's out of scope.
- **Tools** — both built-in and custom MCP tools.
- **Subagents** — first-class via the SDK's `agents` option.
- **Permissions** — auto-approve all tool calls with a hook that's easy to swap for a real policy later.

This guide does **not** re-explain the server stack, the client stack, or how to wire auth. Read `guides/server/README.md` first; this guide extends it.

## Architecture

The SDK runs in-process. One uvicorn worker handles HTTP, SSE, and SDK invocations on the same event loop. Deployment is one image, one process model. Request-scoped resources (DB session, current user, OTel context) are available to tools by closure.

Construct one SDK invocation per **conversation turn**, not one per process. The two SDK entry points are:

- `query(prompt, options)` — stateless async generator. New session each call. Use this for one-shot tasks.
- `ClaudeSDKClient(options)` — stateful client that retains session state across calls. Use this when you want the SDK to manage continuity within a request.

For our shape — a turn arrives over HTTP, runs to completion, persists everything, streams the result, and returns — `query()` with `resume=session_id` from the previous turn is the cleanest fit. The session state we care about lives in Postgres, not in a long-lived Python object.

```python
# src/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agents = build_agent_registry()   # static AgentDefinition map
    yield
    # MCP servers are constructed per request — see "Custom MCP tools".

# src/routers/conversations.py
@router.post("/{conversation_id}/runs")
async def submit_run(
    conversation_id: UUID,
    body: SubmitRunIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    convo = await load_conversation(db, conversation_id, user.id)
    run = await create_run(db, convo, body, user)
    await db.commit()
    return {"run_id": run.id, "stream_url": f"/api/v1/sessions/{convo.id}/runs/{run.id}/stream"}

@router.get("/{conversation_id}/runs/{run_id}/stream")
async def stream_run(...):
    return EventSourceResponse(run_turn(...), media_type="text/event-stream")
```

`run_turn` is an async generator that opens the SDK call, iterates the message stream, persists each event, and yields an SSE event with the persisted event's id. Use [`sse-starlette`](https://github.com/sysid/sse-starlette)'s `EventSourceResponse` — it handles client-disconnect detection and heartbeat pings.

```python
# src/services/agent_runner.py
from claude_agent_sdk import (
    query, ClaudeAgentOptions, HookMatcher,
    AssistantMessage, ToolResultMessage, ResultMessage,
)

async def run_turn(
    db, settings, convo, run, user_input, agent_registry, deps,
) -> AsyncIterator[ServerSentEvent]:
    options = ClaudeAgentOptions(
        agents=agent_registry,
        mcp_servers=[build_knowledge_server(deps)],   # per-request, see Custom MCP tools
        allowed_tools=["Read", "WebSearch", "mcp__knowledge__lookup_doc"],
        hooks={"PreToolUse": [HookMatcher(hooks=[auto_approve])]},
        resume=convo.sdk_session_id,
        max_turns=settings.AGENT_MAX_TURNS,
    )

    async def emit(event_type: str, payload: dict) -> ServerSentEvent:
        row = await persist_event(db, run.id, event_type, payload)
        return ServerSentEvent(id=str(row.id), event=event_type, data=json.dumps(payload))

    yield await emit("run_start", {"run_id": str(run.id), "agent": run.agent_name})
    try:
        async with asyncio.timeout(settings.AGENT_WALL_CLOCK_S):
            async for msg in query(prompt=user_input, options=options):
                if await cancel_requested(db, run.id):
                    run.status = "cancelled"
                    break

                match msg:
                    case AssistantMessage():
                        yield await emit("message", serialize_message(msg))
                    case ToolResultMessage():
                        yield await emit("tool_call_result", serialize_tool_result(msg))
                    case ResultMessage():
                        run.sdk_session_id = msg.session_id
                        run.total_cost_usd = msg.total_cost_usd
                        run.status = "ok"
                        yield await emit("usage", {"total_cost_usd": msg.total_cost_usd})

                if (run.total_cost_usd or 0) > settings.AGENT_MAX_COST_USD:
                    run.status = "cost_capped"
                    break
    except TimeoutError:
        run.status = "timeout"
    except Exception as exc:
        run.status = "error"
        yield await emit("error", {"code": type(exc).__name__, "message": str(exc), "retriable": False})
    finally:
        run.ended_at = datetime.now(UTC)
        await db.commit()
        yield await emit("run_end", {"run_id": str(run.id), "status": run.status, "total_cost_usd": run.total_cost_usd})
```

Two invariants this skeleton enforces:

- **Persist before yield.** `emit` writes `run_events` and only then yields the SSE event with `id=row.id`. The client never sees an event the database doesn't have, so `Last-Event-ID` resume is exact.
- **`finally` always emits `run_end`.** Whether the loop completes, times out, errors, or is cancelled, the client gets a terminal event and can stop the EventSource cleanly.

### Why SSE, not WebSockets

- Traffic is one-directional during a run (server → client). User input arrives on a fresh `POST /runs`.
- SSE rides on plain HTTP — no protocol upgrade, no separate auth path, no special infra at the edge.
- Native reconnection via `Last-Event-ID` is the foundation of stream resumption (see below).
- WebSockets would force us to invent framing and reconnect semantics for no gain.

### Streaming granularity

The Python SDK delivers **whole message objects** (`AssistantMessage`, `ToolResultMessage`, `ResultMessage`), not per-block deltas. The SSE event taxonomy below reflects that: `message` events carry full assistant turns, not character-level chunks.

If you need typewriter-style chat output, you have to bypass the SDK and call the underlying Anthropic streaming API directly — at which point you're effectively on the `claude-api` harness. Don't half-way it. The `agent-sdk` harness is fine for chat where messages appear as units, and it's the natural fit for structured task UIs where the user is waiting on a result, not a typing animation.

### Scaling ceiling

The in-process design has a hard ceiling: each in-flight run holds an asyncio task on a uvicorn worker, and each open SSE connection holds another. Concurrent capacity ≈ `workers × per-worker asyncio throughput`, which is finite — and runs are minutes, not milliseconds.

Knobs while you're under that ceiling:

- Set `--workers` to match host CPU; uvicorn isn't built for thousands of long-lived connections.
- Cap concurrent runs per user at the application layer (rate-limit `POST /runs`).
- Keep `AGENT_WALL_CLOCK_S` short (see Safety valves).

Migration path when you outgrow it: move SDK invocations to a worker pool (`arq`, `SAQ`, Celery). The HTTP layer doesn't change — `POST /runs` enqueues a job; the SSE handler tails `run_events` from Postgres. Persistence schema and event taxonomy stay identical; only `run_turn`'s host moves out of the request handler. Designing the persistence layer this way from day 1 is *why* this migration is later cheap — not why it's avoidable.

## Project layout

Extend the server-guide layout with `agents/` and `mcp_tools/` packages alongside `routers/`, `services/`, `models/`, `schemas/`:

```
app/server/src/
  routers/
    conversations.py     # REST + SSE endpoints
  services/
    agent_runner.py      # opens the SDK call, persists events, emits SSE
    sessions.py          # CRUD on conversations and runs
  agents/
    __init__.py          # registry: name -> AgentDefinition
    <agent_name>/
      __init__.py        # builds AgentDefinition from prompt + tools
      prompt.md          # system prompt, authored as Markdown
  mcp_tools/
    __init__.py          # exports build_*_server(deps) factories per tool group
    <tool_group>.py      # @tool functions + build_<group>_server(deps) factory
  models/
    conversation.py      # Conversation, Message, AgentRun, ToolCall, RunEvent
  schemas/
    conversation.py      # request/response models + SSE event payloads
```

The agent definition (system prompt + tool roster + subagent map) is its own concern; don't bury it in `services/`.

## Defining agents

Agents are `AgentDefinition` instances, registered by name. Load the system prompt from a `prompt.md` file at import time and compute its SHA-256:

```python
# src/agents/researcher/__init__.py
from pathlib import Path
from hashlib import sha256
from claude_agent_sdk import AgentDefinition

PROMPT = (Path(__file__).parent / "prompt.md").read_text()
PROMPT_SHA = sha256(PROMPT.encode()).hexdigest()

definition = AgentDefinition(
    description="Researches a topic and produces a structured brief.",
    prompt=PROMPT,
    tools=["Read", "WebSearch", "WebFetch"],
    model="sonnet",
)
```

Persist `prompt_sha` on every `agent_runs` row. Evaluations group by `prompt_sha`, not by agent name — that's how you tell whether a regression came from a prompt change or something else. Files (not strings) for prompts because they diff cleanly in code review and embed examples without escaping.

Subagents are declared the same way and passed via `ClaudeAgentOptions(agents={"reviewer": reviewer.definition, ...})`. The parent agent delegates by name; the SDK manages the dispatch.

## Custom MCP tools

Define tools with the SDK's `@tool` decorator and register them on an MCP server with `create_sdk_mcp_server`. **MCP servers are constructed per request, not at lifespan**, because tools close over request-scoped resources (`AsyncSession`, `current_user`). Construction is cheap — `create_sdk_mcp_server` is a function call, not a network handshake.

```python
# src/mcp_tools/knowledge.py
from claude_agent_sdk import tool, create_sdk_mcp_server

def build_knowledge_server(deps: ToolDeps):
    @tool(
        "lookup_doc",
        "Fetch a document from the knowledge base by id.",
        {"doc_id": str},
    )
    async def lookup_doc(args: dict) -> dict:
        row = await deps.db.get(Document, args["doc_id"])
        if row is None or row.user_id != deps.user.id:
            return {"content": [{"type": "text", "text": "not found"}], "is_error": True}
        return {"content": [{"type": "text", "text": row.body}]}

    return create_sdk_mcp_server(name="knowledge", version="1.0.0", tools=[lookup_doc])
```

Two conventions worth following:

- **Request-scoped deps via closure**, not globals. The router resolves `AsyncSession`, `current_user`, and any other request-scoped resource through `Depends`, hands them to `agent_runner.run(...)`, which calls `build_*_server(deps)` per request. Tool signatures take only LLM-supplied arguments. The model can't spoof tenancy because it can't reach `deps.user`.
- **Return `is_error: True` on tool failures**, don't raise. The SDK surfaces tool errors to the model as tool results so the agent loop can recover. Reserve raised exceptions for actual bugs.

Built-in tools (Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, etc.) are enabled by listing them in `allowed_tools` on `ClaudeAgentOptions`. Be deliberate about which to expose — `Bash` on a server is broad authority.

## Permissions

Auto-approve every tool call via a `PreToolUse` hook:

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

async def auto_approve(input_data, tool_use_id, context):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }

options = ClaudeAgentOptions(
    hooks={"PreToolUse": [HookMatcher(hooks=[auto_approve])]},
    ...
)
```

Future restrictions (per-user denylists, rate limits, human-in-the-loop) swap the hook body, not the wiring. Persist every approval decision (the `tool_calls` row records the call regardless) so you can replay historical traffic against a stricter policy before rolling it out.

## Safety valves

Three ceilings every run respects, configured in `Settings`:

- **`AGENT_MAX_TURNS`** — hard cap on agent loop iterations. Passed to `ClaudeAgentOptions(max_turns=...)`. Default: 25.
- **`AGENT_WALL_CLOCK_S`** — wall-clock timeout. `run_turn` wraps the SDK iteration in `asyncio.timeout()`. Default: 180s.
- **`AGENT_MAX_COST_USD`** — per-run cost ceiling, checked against the running `total_cost_usd` after each `ResultMessage`. Default: $1.00.

When a cap trips, `agent_runs.status` records *which* (`timeout`, `cost_capped`, `turns_exceeded`) so dashboards distinguish runaway loops from expensive-but-legitimate runs. Tune defaults per agent if needed (researcher agents legitimately cost more than a chat concierge), but never leave any of the three uncapped.

### Cancellation

`POST /sessions/{id}/runs/{run_id}/cancel` sets `agent_runs.cancel_requested_at = now()` and returns `202` immediately. `run_turn` polls this column between SDK message iterations and breaks the loop when set, recording `status = 'cancelled'` and emitting `run_end`.

Cooperative because the SDK's `query()` async generator yields at message boundaries — there's no way to interrupt mid-tool-call without killing the worker. Worst-case cancellation latency is the duration of the in-flight tool call. If you need hard cancel, run the SDK in a worker pool (see Scaling ceiling) where you can terminate the job process.

## Persistence schema

Multi-tenant isolation is by `user_id` on every top-level table, populated from the `current_user` dependency. No row is read or written without a user-scoped query — enforced in `services/`, not `routers/`. Add Postgres RLS later if you want defense in depth.

Tables (shape only — write the migration yourself):

- **`conversations`** — `id`, `user_id`, `title`, `created_at`, `updated_at`, `metadata jsonb`. Index `(user_id, updated_at desc)`.
- **`messages`** — `id`, `conversation_id`, `role` (`user` | `assistant` | `system` | `tool`), `content jsonb`, `created_at`. Index `(conversation_id, created_at)`.
- **`agent_runs`** — one row per SDK invocation. `id`, `conversation_id`, `parent_run_id` (nullable, self-FK for subagents), `agent_name`, `prompt_sha`, `model`, `status` (`running` | `ok` | `error` | `cancelled` | `timeout` | `cost_capped` | `turns_exceeded`), `started_at`, `ended_at`, `cancel_requested_at` (nullable, set by `POST .../cancel`), `total_cost_usd`, `sdk_session_id` (for resume). Index `(conversation_id, started_at)` and `(parent_run_id)`. Add a partial unique index `(conversation_id) WHERE status = 'running'` to enforce the concurrency policy below.
- **`tool_calls`** — `id`, `run_id`, `name`, `input jsonb`, `output jsonb`, `status` (`ok` | `error`), `started_at`, `ended_at`, `duration_ms`. Index `(run_id, started_at)`.
- **`run_events`** — append-only SSE replay log. `id` (monotonic), `run_id`, `seq`, `type`, `payload jsonb`, `created_at`. Index `(run_id, id)`. Use Postgres declarative partitioning by `created_at` day so pruning is `DROP TABLE run_events_YYYY_MM_DD` (O(1)) instead of bulk `DELETE` (O(n) plus index bloat). [`pg_partman`](https://github.com/pgpartman/pg_partman) automates partition creation. A 7-day retention window is a reasonable default; extend it if eval replay matters.

The SDK exposes `total_cost_usd` on the final `ResultMessage` but **not** per-turn input/output token counts. Persist what you have; don't fabricate token columns. If you need per-call token data later, you'll have to instrument by intercepting the underlying API calls.

`run_events` is written on the same code path that emits SSE: persist the row, then yield the event with `id=row.id`. The client never sees an event the database hasn't.

## HTTP / SSE API surface

All routes mounted under `/api/v1`, scoped to `current_user`. Sessions not owned by the caller return `404`, not `403` — don't leak existence.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/sessions` | Create a conversation. Returns `Session`. |
| `GET` | `/sessions` | List the caller's sessions. Cursor-paginated, newest first. |
| `GET` | `/sessions/{id}` | Fetch one session header. |
| `GET` | `/sessions/{id}/messages` | Full message + event history, cursor-paginated. |
| `PATCH` | `/sessions/{id}` | Rename, archive, edit metadata. |
| `DELETE` | `/sessions/{id}` | Soft-delete. |
| `POST` | `/sessions/{id}/runs` | Submit a turn. Idempotent on `Idempotency-Key`. Returns `{run_id, stream_url}`. |
| `GET` | `/sessions/{id}/runs/{run_id}/stream` | SSE. Supports `Last-Event-ID` for resume. |
| `POST` | `/sessions/{id}/runs/{run_id}/cancel` | Cooperative cancel. |

The split between `POST /runs` and `GET .../stream` lets the client kick off a run, persist `run_id`, and reconnect to the stream after a refresh without resubmitting.

### Concurrency policy

Only one run per conversation may be `running` at a time. Enforced by the partial unique index on `agent_runs` (see Persistence schema):

```sql
CREATE UNIQUE INDEX one_active_run_per_conversation
  ON agent_runs (conversation_id)
  WHERE status = 'running';
```

A `POST /runs` against a conversation with an in-flight run returns `409 Conflict` with the existing `run_id` and `stream_url` in the body. Clients display the live stream for that run rather than retrying.

### `Idempotency-Key`

Optional header on `POST /runs`. The server stores `(user_id, key) → run_id` for 24h; a duplicate within that window returns the original `{run_id, stream_url}` instead of creating a new run. Guards against accidental double-submits (refresh, retry-on-flaky-network). Keys are client-generated (UUIDv4 is fine); the server treats them as opaque.

### One endpoint, two input shapes

`POST /runs` accepts a discriminated union on `input.kind`. Same endpoint serves chat and structured-task UIs:

```json
{ "input": { "kind": "chat", "content": "Plot last 30 days of signups." } }

{ "input": { "kind": "task", "task_type": "research_brief",
             "params": { "topic": "EU AI Act", "depth": "deep" } } }
```

Splitting at the HTTP boundary just to mirror UI shapes leaks UI concerns into the contract and forces duplicate plumbing for resume, cancel, and history. The runtime path is identical: render the input into a turn, hand it to the SDK, stream the result. The server validates `params` against a registered Pydantic schema per `task_type`.

### SSE event taxonomy

Each event has a name (`event:`), a JSON payload (`data:`), and a monotonic id (`id:`, the persisted `run_events.id`).

| Event | Payload |
|---|---|
| `run_start` | `{run_id, parent_run_id?, agent}` |
| `message` | `{message_id, role, content, parent_run_id?}` |
| `tool_call_start` | `{tool_call_id, name, input, parent_run_id?}` |
| `tool_call_result` | `{tool_call_id, status, output, duration_ms}` |
| `subagent_start` | `{subagent_run_id, parent_run_id, agent}` |
| `subagent_end` | `{subagent_run_id, status, summary}` |
| `usage` | `{total_cost_usd}` |
| `error` | `{code, message, retriable}` |
| `run_end` | `{run_id, status, total_cost_usd}` |

`message` is whole-message, not per-token, per the streaming-granularity note above. Subagent events appear inline on the parent stream — verify the exact ordering and which message types the SDK emits for subagent activity by running a subagent and observing the message stream; adjust the persistence and replay code to match. Both top-level and subagent events carry `parent_run_id` so the client can build the tree.

## Resumption

Two layers:

- **SDK session resume** — capture `sdk_session_id` from the first turn's `ResultMessage`, persist it on `agent_runs`, and pass `resume=sdk_session_id` in `ClaudeAgentOptions` for the next turn in the same conversation. The SDK rehydrates its session state.
- **SSE stream resume** — a reconnecting client sends `Last-Event-ID: <n>`. The handler queries `run_events` for that run where `id > n`, replays them as SSE, and — if the run is still in flight — attaches to the live tail. Completed runs replay to `run_end` and close.

Resuming a *conversation* (not just a connection) is `GET /sessions/{id}/messages` for history, then `POST /sessions/{id}/runs` for the next turn. The same event objects come back from history that the SSE stream emitted, so the client's reducer is identical for live and replayed events.

## Client consumer

The full client stack lives in `guides/client/README.md`; the SSE consumption shape for *this harness* is:

```ts
// Submit a turn and stream events.
const { run_id, stream_url } = await post(
  `/api/v1/sessions/${conversationId}/runs`,
  { input: { kind: "chat", content } },
);

const es = new EventSource(stream_url, { withCredentials: true });

const types = [
  "run_start", "message", "tool_call_start", "tool_call_result",
  "subagent_start", "subagent_end", "usage", "error", "run_end",
];
for (const t of types) {
  es.addEventListener(t, (e) =>
    dispatch({ type: t, payload: JSON.parse(e.data), id: e.lastEventId }),
  );
}
es.addEventListener("run_end", () => es.close());
```

The reducer keyed on `event.type` is the *same one* used to render history fetched from `GET /sessions/{id}/messages` — persisted events replay through identical code. To resume after a refresh: read the persisted `run_id` and `stream_url`, attach a new `EventSource`, and the browser's automatic `Last-Event-ID` reconnect causes the server to replay from `run_events` where `id > Last-Event-ID`.

Native `EventSource` doesn't expose request headers (no auth header injection, no POST body). If your auth depends on bearer tokens rather than cookies, use a `fetch + ReadableStream` consumer instead — see `guides/client/README.md`'s SSE notes.

## Testing

Extend the unit/integration split from the server guide:

- `tests/unit/agents/` — prompt loading, hash stability, registry wiring, schema round-trips.
- `tests/unit/mcp_tools/` — each tool tested as a plain async function with a transactional `AsyncSession` fixture and a fake deps object. No SDK involvement.
- `tests/integration/agents/` — full agent runs against a **mocked model**. Stub the SDK transport to replay scripted assistant messages (text + tool_use blocks + stop reasons). Assert on what was persisted: messages, tool calls, run status, recorded events. Verify the exact mock seam against the SDK's current internals.
- `tests/integration/agents/recorded/` — a small set of runs against the real model, gated behind `RUN_LIVE=1`, run nightly. These catch prompt regressions; the mocked tests catch wiring regressions.

Avoid running every CI build against a real model. Non-determinism makes failures noisy and erodes trust in the suite.

## Observability

Open an OTel span `agent.run` for each SDK invocation with attributes `agent.name`, `agent.run_id`, `user.id`, `prompt.sha`, `model.name`. Each tool call is a child span `agent.tool` with `tool.name`, `tool.duration_ms`, `tool.status`. Bind the same fields into structlog at the start of the request via `structlog.contextvars.bind_contextvars(...)` so every log line in the run carries them.

`total_cost_usd` rolls up onto the `agent_runs` row at completion. That row plus its `tool_calls` and `run_events` children is the unit of evaluation; the OTel trace is the time-ordered view of the same data. Together they make any failed or surprising run reproducible without re-running the model. Turning that unit into a regression suite is covered in [`guides/evals/README.md`](../../evals/README.md).

## What this guide does not cover

- **Server stack** (FastAPI, SQLAlchemy, Postgres, uv, lint, test, deploy) — `guides/server/README.md`.
- **Client UI** (React/TS, SSE consumption, rendering tool-call and subagent events) — `guides/client/README.md`.
- **Auth** — bring your own. Wire it in as a FastAPI dependency that resolves `current_user`. Everything in this guide assumes that exists.
- **Individual agents** (system prompts, tool rosters, subagent topology for *your* product) — that's per-project content under `app/server/src/agents/`, not part of the harness playbook.
- **Evals** — turning persisted runs into a regression suite — [`guides/evals/README.md`](../../evals/README.md).

## References

- SDK source — https://github.com/anthropics/claude-agent-sdk-python
- SDK overview — https://code.claude.com/docs/en/agent-sdk/overview
- Quickstart — https://code.claude.com/docs/en/agent-sdk/quickstart
- Python reference — https://code.claude.com/docs/en/agent-sdk/python
- Custom tools — https://code.claude.com/docs/en/agent-sdk/custom-tools
- Hooks — https://code.claude.com/docs/en/agent-sdk/hooks
- Sessions — https://code.claude.com/docs/en/agent-sdk/sessions
- Subagents — https://code.claude.com/docs/en/agent-sdk/subagents
