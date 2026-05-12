# Claude API Harness Guide

Playbook for initializing an agentic engineering project that uses Anthropic's Claude API and builds a custom harness, interacted with through the application interface.

> **Status: planning sketch.** This file is an outline for the eventual guide, not the guide itself. The structure below mirrors `guides/harnesses/agent-sdk/README.md` where the answer is the same; it diverges where building the loop yourself changes the answer. Replace this notice with the real content as sections are written.

## Framing

`claude-api` is the same shape as `agent-sdk` (FastAPI server + SPA client, multi-user, persisted, SSE streaming) — but you own the agent loop. Default to mirroring the `agent-sdk` guide's structure; only diverge where building the loop yourself changes the answer. That keeps the two guides comparable.

**Tone target.** Code-heavy, not narrative. Skip prompt-engineering theory and evals — those are application-layer concerns covered elsewhere. Thread one realistic scenario through the guide (e.g. a 5-turn conversation that exercises streaming, a tool call on turn 2, a cache hit on turn 3, an extended-thinking request on turn 4) so each section extends a working example rather than introducing a new toy problem.

**Section order is by implementation milestone, not by API surface.** A builder should be able to read top-to-bottom and have a working harness at each section's end.

**Complexity compounds.** A loop with 20 LLM decision points at 95% per-step accuracy is 36% reliable end-to-end. Each tool dispatch, reasoning step, and subagent call multiplies failure probability; deterministic code doesn't. Default to the smallest loop that solves the problem and grow it only when evals demand it. The sections below describe the full surface area, not the order in which to add complexity.

## Planned sections

### Core loop (build these first, in order)

1. **When to choose this harness** — listed in rough priority order:
   - **Explicit prompt-cache control.** The biggest cost lever in the harness; the SDK's cache behavior is opaque. This is *the* reason most teams reach for the raw API.
   - **No `claude-agent-sdk` pin in the server image.** Slimmer dependency surface for ops teams who don't want a fast-moving SDK on the critical path.
   - **Block-level access for extended thinking + interleaved tool use.** Reaching into `thinking` / `text` / `tool_use` block ordering is the SDK's weak spot.
   - **Batch API access** for non-interactive workloads (50% off).
   - **Per-token streaming** (`content_block_delta` text + `input_json_delta` tool args). Real, but a thin reason on its own.
   - **Custom tool dispatch policies** and raw `usage` data the SDK hides.
2. **Assumed constraints** — same stack as agent-sdk; explicit non-goal: this guide doesn't re-derive the server/client guides, doesn't teach prompt engineering, doesn't cover evals or RAG.
3. **Architecture — the agent loop** — the big swap. No `query()` / `ClaudeSDKClient`. Instead: a hand-rolled async loop around `anthropic.AsyncAnthropic().messages.stream(...)` that walks the response's content-block list, dispatches `tool_use` blocks to a tool registry, appends `tool_result` blocks (each carrying the originating `tool_use_id`), and re-enters the loop. Show one concrete skeleton end-to-end, not fragments. Cover:
   - **Loop-exit conditions.** Continue on `stop_reason == "tool_use"`. Handle `pause_turn` (server-side tool-sampling hit its iteration cap — re-send the response as-is to let Claude continue). Surface `refusal` and `model_context_window_exceeded` as terminal.
   - **Multi-block response handling.** The response is *always* a list of content blocks (`thinking`, `text`, `tool_use`, possibly more). Never index `[0]` blindly.
   - **System prompt as a list of blocks**, not a string — it's the shape that makes caching, persistence, and tool presentation downstream work cleanly. Commit to this shape in the skeleton.
   - **Retries, `request_id`, and rate limits.** The SDK retries 429/529/overload for you; your loop doesn't get that free. Wrap each call with bounded retry + jittered backoff; log `request_id` from response headers on every call (Anthropic support can't help without it).
4. **Tools** — plain async functions in a registry keyed by name. Default to Pydantic models → JSON schema (one-liner); hand-rolled schema is the escape hatch. No MCP authoring; no SDK `@tool` indirection. Closure-over-deps pattern for tenancy safety. Tool errors return `{"type": "tool_result", "tool_use_id": ..., "is_error": True, "content": ...}` rather than throwing — call this out, since it's easy to get wrong. Keep `content` minimal: return only what the next turn needs, not the full upstream API payload. LLMs degrade on info parked in the middle of long contexts (Liu et al., *Lost in the Middle*); a fat tool result pushes the next user turn into that dead zone. End with a short subsection on **built-in tools** (`web_search`, `text_editor`, `code_execution`, etc.) — schemas Anthropic provides; you don't implement the body. One paragraph each so builders know the escape hatches exist.
5. **Permissions** — pre-dispatch hook between tool lookup and tool invocation. Belongs here, not in ops, because in a hand-rolled loop the hook *is* the dispatch site — you can't write Tools (§4) without deciding the allow/deny ceremony. Same swap-the-body story as agent-sdk; the multi-tenant `deps.user` closure check lives here too. Frame this as the *only un-evadable* safety layer: prompt-level instructions and LLM-judge guardrails both have published bypass rates near 100% under adversarial input. Code at the dispatch site is the guarantee; everything else is defense-in-depth. If a check is itself an LLM call (e.g. "does this output leak PII?"), validate the judge against expert-labeled examples before shipping, and track precision and recall separately — raw agreement is misleading on imbalanced data.
6. **Streaming** — *here* you do get per-token deltas. Use the `.stream()` context manager (cleaner than `messages.create(stream=True)`; it gives you `text_stream` and `get_final_message()`). Cover the event taxonomy: `message_start`, `content_block_start`, `content_block_delta` (text deltas), `input_json_delta` (tool-use argument deltas), `thinking_delta` + `signature_delta` (when extended thinking is on), `content_block_stop`, `message_delta` (final `stop_reason` + `usage`), `message_stop`.
7. **Extended thinking** — Core, not an extension: Sonnet/Opus 4.x is routinely run with thinking on, response structure gains a `thinking` block before `text`, and naive persistence/streaming code crashes on first real run if it isn't covered before the builder ships. **Default: per-call opt-in, default off.** Cover: thinking budget parameter; incompatibility with prefill and `temperature`; caching interaction (system-prompt cache persists across thinking-param changes; message-prompt cache invalidates).
8. **Prompt caching** — doesn't exist in agent-sdk guide. With direct API access you control `cache_control` markers explicitly; this is the biggest cost lever in the harness. Frame as "the first optimization, not a correctness requirement" — your harness already runs without it. Cover:
   - Cache ordering (tools → system → messages).
   - **Minimum cacheable tokens is model-dependent**, not a flat 1024: **4096** for Opus 4.7/4.6/4.5 and Haiku 4.5; **2048** for Sonnet 4.6 and Haiku 3.5; 1024 only for Sonnet 4.5 and earlier.
   - Single-character sensitivity for cache hits.
   - Four explicit breakpoint limit.
   - Reading `cache_creation_input_tokens` vs `cache_read_input_tokens` from `usage`.
   - The "copy tools, mark the last one" idiom; recommended default breakpoint placement (last tool + last system block + last user turn before tool results).
9. **Persistence schema** — nearly identical to agent-sdk. Differences: drop `sdk_session_id` (no SDK session — *you* are the session, replaying message history each turn); add per-call token columns (input, output, cache-creation, cache-read) since you have the data; store `stop_reason` since you decide what to do with it; serialize/deserialize the full content-block list (including `thinking` blocks where applicable) into and out of the `messages=[...]` shape, not just text. **Memory governance** (callout for when persisted history outlives a single turn or is shared across users or agents): define what decays (stale tool results, old context), how conflicts resolve (newer-wins, voting, manual review), and who can write. Unmanaged shared memory is both a quality problem (drift, contradiction) and a security one — adversarial input in session N poisons session N+1.
10. **Resumption** — conversation resume = replay persisted messages into `messages=[...]` on the next call. Reinforce "Claude stores nothing" as the load-bearing mental model. SSE stream resume identical to agent-sdk.
11. **HTTP/SSE API surface** — copy from agent-sdk; add token-delta events to the taxonomy and an event for tool-use argument streaming. Inherit `Idempotency-Key` handling and multi-tenant `user_id` scoping from agent-sdk — don't silently drop them.

### Extensions (opt in based on project needs)

12. **Multi-modal & file input** — base64 image blocks (size/dimension limits, token cost per image) plus the Files API for larger or reusable assets (`file_id` references). Code execution as Claude's built-in tool running in isolated containers is the natural pairing for files. Architectural decision (not a footnote): changes how you handle large user data and what you expose to the agent loop.
13. **Citations** — first-class structured source attribution for PDF/document workflows. Skip if the project doesn't analyze documents; otherwise it's the right primitive for "show your sources."
14. **Batch API** — ~50% cost reduction for non-interactive workloads. Async submission, results polled or webhooked. Opt-in cost lever for offline jobs (overnight summarization, eval runs); irrelevant for interactive turns.

### Safety, control, and ops

15. **Subagents** — *you* implement them. Either nested loops in-process or a recursive `run_turn`. Cover the topology, how parent/child runs link via `parent_run_id`, and a **hard depth cap of 3** before the cost cap trips. **Cost first:** group-chat topologies multiply tokens ~30-40×, orchestrator ~3×, pipeline 1.5-3× — and cost is O(N²) on shared context, not linear. Most "this needs multi-agent" intuitions don't survive a cost budget; default to a single loop until evals say otherwise. **Interface, not role:** define what a subagent returns to its parent (and what the parent passes in) as a Pydantic model, not free-form text. Research on multi-agent systems (MetaGPT and successors) finds typed handoff artifacts ~3× more impactful than role specialization — the interface *is* the architecture.
16. **Safety valves** — turns, wall-clock, cost. Cost you compute yourself from `usage.input_tokens` / `output_tokens` / cache token counts × model pricing. **Pricing table lives as a checked-in dict in `Settings` keyed by model name**, including cache-creation and cache-read rates; refreshed when models change.
17. **Cancellation** — same cooperative pattern, but you can cancel mid-stream (between deltas), not just between messages. Better than agent-sdk on this axis.
18. **Testing** — same split as agent-sdk. "Mock the SDK transport" becomes "mock `messages.stream`" — easier, since the API surface is narrower. Show fixtures for streamed responses including `thinking_delta` events.
19. **Observability** — same OTel/structlog story; add token + cache-hit counters, per-call cost, stream-event counters, and `request_id` on every log line since you have them.
20. **What this guide does not cover** — same disclaimers as agent-sdk (server stack, client UI, auth, individual agents). Add: prompt engineering, evals, RAG, MCP server *authoring* (consuming MCP servers from your harness is fine and is covered under tools).

## Open questions to resolve before drafting

- **Token streaming default on or off?** It's a headline capability but adds client complexity. Lean toward defaulting on and noting how to suppress.
- **Multi-modal scope — gate behind a feature flag?** If most projects don't need vision, §12 can stay as "here's how if you need it" rather than wiring it into the default loop.
- **Built-in tools — recommend or just mention?** Web search in particular is tempting as a default; needs a stance on when to reach for it vs. building your own retrieval.

## References

- https://www.anthropic.com/learn/build-with-claude
- https://platform.claude.com/docs/en/api/overview
