"""Claude-API overlay: produce a fresh run for one golden case.

This is the `claude-api` harness overlay of the eval scaffold. At kickstart it is
copied on top of the shared core into `app/server/src/evals/` (see
`guides/evals/templates/README.md` and KICKSTART.md Phase 2). It is INERT in the
kit repo: it imports app modules (the hand-rolled agent loop, `Settings`, the
concierge prompt) that do not exist until a project is kickstarted, so it is
excluded from any kit-level lint/type gate. Every app touchpoint is a
`# TODO(kickstart)` seam.

Contract: `produce_run(case) -> RunRecord`. Drive the concierge through the
hand-rolled Claude API loop (the `claude-api` harness) against
`case.input.content`, then map the loop's output into the shared `RunRecord`.

Unlike the agent-sdk overlay, the hand-rolled loop exposes the full final
`message_delta` (`stop_reason`) and `usage` (input/output tokens), and computes
per-run cost from the `Settings` pricing table — so this overlay POPULATES
`stop_reason`, `input_tokens`, `output_tokens`, and `cost_usd`. The optional
`claude_api/extra_assertions.py` checks those fields; agent-sdk ships no such
file because it cannot fill them.

`prompt_sha` is supplied by THIS overlay (not the shared loader): the claude-api
harness builds its system prompt as a list of blocks
(see `guides/harnesses/claude-api/README.md`), so the sha is computed over that
serialized block list, not a single `prompt.md` string.
"""

from __future__ import annotations

import json
from hashlib import sha256

# ToolCallRecord is referenced by the RunRecord mapping you uncomment at
# kickstart (see produce_run below); keep the import so the seam is ready.
from .models import GoldenCase
from .run_contract import RunRecord, ToolCallRecord  # noqa: F401


def _block_prompt_sha() -> str:
    """Hash the concierge's block-style system prompt.

    The claude-api harness commits to a system prompt that is a *list of blocks*,
    not a string. Serialize the blocks deterministically (sorted keys) before
    hashing so the sha is stable across runs and matches the persisted
    `agent_runs.prompt_sha`.

    TODO(kickstart): import the concierge's actual system-prompt blocks, e.g.
    `from app.server.src.agents.concierge import SYSTEM_PROMPT_BLOCKS`, and hash
    those instead of the placeholder below.
    """
    system_prompt_blocks: list[dict] = []  # TODO(kickstart): the real blocks.
    serialized = json.dumps(system_prompt_blocks, sort_keys=True, ensure_ascii=False)
    return sha256(serialized.encode("utf-8")).hexdigest()


def produce_run(case: GoldenCase) -> RunRecord:
    """Run the concierge via the hand-rolled API loop and map to a RunRecord."""
    # TODO(kickstart): drive the hand-rolled agent loop against the case input.
    # The claude-api harness owns its loop around `messages.stream(...)`: it
    # walks the content-block list, dispatches `tool_use` blocks to the tool
    # registry, appends `tool_result` blocks, and re-enters until `stop_reason`
    # is terminal. For evals we want one self-contained invocation, e.g.:
    #
    #     from app.server.src.config import get_settings
    #     from app.server.src.services.agent_loop import run_once
    #     from app.server.src.agents.concierge import system_prompt_blocks, tools
    #     settings = get_settings()
    #     result = await run_once(
    #         system=system_prompt_blocks,
    #         tools=tools,
    #         user_content=case.input.content,
    #         settings=settings,
    #     )
    #
    # `result` is expected to expose: the ordered tool calls (name, input, and
    # the tool_result content), the final assistant text, the terminal
    # `stop_reason`, and `usage` (input/output tokens). Cost is computed by the
    # loop (or here) from the `Settings` pricing dict keyed by model name
    # (see guides/harnesses/claude-api/README.md, "Safety valves").
    #
    # The shared runner calls `produce_run(case)` SYNCHRONOUSLY. If the loop is
    # async, wrap it with `asyncio.run(...)` *inside* this function rather than
    # making this `async def` (the runner does not await its return value).
    raise NotImplementedError(
        "TODO(kickstart): drive the hand-rolled Claude API loop against "
        "case.input.content, then map the result below."
    )

    # The mapping below documents the exact RunRecord the graders expect.
    # Unreachable today on purpose (the raise above).
    #
    # tool_calls = [
    #     ToolCallRecord(
    #         name=call.name,
    #         input=call.input,
    #         # Coerce the tool_result content to its serialized string form so
    #         # `result_contains` / `include_tool_results` can match against it.
    #         output=_as_text(call.result_content),
    #     )
    #     for call in result.tool_calls
    # ]
    # return RunRecord(
    #     status="ok" if result.stop_reason == "end_turn" else "error",
    #     tool_calls=tool_calls,
    #     final_text=result.final_text,
    #     prompt_sha=_block_prompt_sha(),
    #     # claude-api populates these (agent-sdk leaves them None):
    #     stop_reason=result.stop_reason,
    #     input_tokens=result.usage.input_tokens,
    #     output_tokens=result.usage.output_tokens,
    #     cost_usd=result.cost_usd,
    # )


def _as_text(content: object) -> str:
    """Coerce a `tool_result` content payload to a serialized string.

    TODO(kickstart): match this to how the loop stores tool_result content.
    Tool results are typically content-block lists
    (`[{"type": "text", "text": ...}]`); extract and join the text, or
    `json.dumps` a structured payload. Keep it a plain string so substring
    checks work.
    """
    if isinstance(content, str):
        return content
    return str(content)
