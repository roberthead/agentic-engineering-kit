"""Agent-SDK overlay: produce a fresh run for one golden case.

This is the `agent-sdk` harness overlay of the eval scaffold. At kickstart it is
copied on top of the shared core into `app/server/src/evals/` (see
`guides/evals/templates/README.md` and KICKSTART.md Phase 2). It is INERT in the
kit repo: it imports app modules (`app.server.src.agents...`, the agent runner)
that do not exist until a project is kickstarted, so it is excluded from any
kit-level lint/type gate. Every app touchpoint is a `# TODO(kickstart)` seam.

Contract: `produce_run(case) -> RunRecord`. Drive the concierge through the
Claude Agent SDK against `case.input.content`, then map the SDK result into the
shared `RunRecord` the graders consume. The SDK surfaces `total_cost_usd` on the
final `ResultMessage` but NOT per-turn token counts, so `stop_reason`,
`input_tokens`, `output_tokens`, and `cost_usd` are left `None` here — the
claude-api overlay is the one that populates them.

`prompt_sha` is supplied by THIS overlay (not by the shared loader): the
agent-sdk idiom hashes the concierge `prompt.md` at import time, mirroring the
`PROMPT_SHA` constant the agent definition already computes
(see `guides/harnesses/agent-sdk/README.md`).
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

# ToolCallRecord is referenced by the RunRecord mapping you uncomment at
# kickstart (see produce_run below); keep the import so the seam is ready.
from .models import GoldenCase
from .run_contract import RunRecord, ToolCallRecord  # noqa: F401

# --- prompt_sha seam -------------------------------------------------------
#
# The agent-sdk harness already computes `PROMPT_SHA` next to the agent
# definition. Prefer importing that constant so the eval and the persisted
# `agent_runs.prompt_sha` agree byte for byte:
#
#     TODO(kickstart): from app.server.src.agents.concierge import PROMPT_SHA
#
# The helper below is an ILLUSTRATION of the same hash, not a drop-in fallback:
# once copied this file lives at `app/server/src/evals/produce_run.py`, so the
# concierge prompt is at `../agents/concierge/prompt.md` (i.e. `parents[1]`,
# the `src/` root). Confirm the real path at kickstart.
_CONCIERGE_PROMPT_PATH = (
    # TODO(kickstart): point at the real concierge prompt (src/agents/concierge/).
    Path(__file__).resolve().parents[1] / "agents" / "concierge" / "prompt.md"
)


def _concierge_prompt_sha() -> str:
    prompt = _CONCIERGE_PROMPT_PATH.read_text(encoding="utf-8")
    return sha256(prompt.encode("utf-8")).hexdigest()


def produce_run(case: GoldenCase) -> RunRecord:
    """Run the concierge via the Agent SDK and map the result to a RunRecord."""
    # TODO(kickstart): invoke the concierge through the app's agent runner.
    # The runner (`app.server.src.services.agent_runner`) opens the SDK call,
    # persists the `agent_runs` / `tool_calls` rows, and returns the final
    # result. For evals we want a single, self-contained invocation against the
    # case input — not an HTTP round-trip. Wire it to whatever entry point the
    # runner exposes for a one-shot run, e.g.:
    #
    #     from app.server.src.services.agent_runner import run_once
    #     from app.server.src.agents.concierge import definition
    #     result = await run_once(definition, case.input.content)
    #
    # The shared runner calls `produce_run(case)` SYNCHRONOUSLY (it does not
    # await). The Agent SDK is async-first, so wrap the async call with
    # `asyncio.run(...)` *inside* this sync function, e.g.
    # `result = asyncio.run(run_once(definition, case.input.content))`.
    # (Do NOT make this `async def` — the runner would then get an un-awaited
    # coroutine. TODO(kickstart): confirm the SDK runner's call convention.)
    raise NotImplementedError(
        "TODO(kickstart): drive the concierge via the Agent SDK runner against "
        "case.input.content, then map the result below."
    )

    # The mapping below is the shape to fill in once `result` is available.
    # It is unreachable today on purpose (the raise above), but documents the
    # exact RunRecord the graders expect.
    #
    # tool_calls = [
    #     ToolCallRecord(
    #         name=call.name,
    #         input=call.input,
    #         # Coerce each tool result to its serialized string form so the
    #         # shared assertions' `result_contains` / the judge's
    #         # `include_tool_results` can substring-match against it.
    #         output=_as_text(call.output),
    #     )
    #     for call in result.tool_calls
    # ]
    # return RunRecord(
    #     status="ok" if result.status == "ok" else result.status,
    #     tool_calls=tool_calls,
    #     final_text=result.final_text,
    #     prompt_sha=_concierge_prompt_sha(),
    #     # Left None: the SDK does not surface these cleanly.
    #     stop_reason=None,
    #     input_tokens=None,
    #     output_tokens=None,
    #     cost_usd=None,
    # )


def _as_text(output: object) -> str:
    """Coerce a tool result to the serialized string form the contract wants.

    TODO(kickstart): match this to how the SDK surfaces tool results. SDK tool
    results are content-block lists (`[{"type": "text", "text": ...}]`); extract
    and join the text, or `json.dumps` a structured payload. Keep it a plain
    string so `result_contains` substring checks work.
    """
    if isinstance(output, str):
        return output
    return str(output)
