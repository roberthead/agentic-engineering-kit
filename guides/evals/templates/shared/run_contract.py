"""The persisted-run contract the graders read.

This is the seam between *how a run is produced* (harness-specific, lives in the
overlay's ``produce_run.py``) and *how a run is graded* (harness-agnostic, lives
in ``assertions.py`` / ``judge.py``). The graders consume a ``RunRecord`` and
nothing else — they never touch raw ``agent_runs`` columns — so the same shared
grader code serves both the ``agent-sdk`` and ``claude-api`` harnesses.

The overlay's ``produce_run.py`` is responsible for mapping its harness output
into a ``RunRecord``. In particular it coerces each tool result to its
serialized *string* form for ``ToolCallRecord.output`` (that is what
``result_contains`` / ``include_tool_results`` match against) and injects the
``prompt_sha`` — the shared loader never computes it.
"""

from pydantic import BaseModel


class ToolCallRecord(BaseModel):
    name: str
    input: dict[str, object]
    output: str  # the overlay's produce_run.py coerces the tool result to its serialized string form


class RunRecord(BaseModel):
    status: str  # "ok" or an error string
    tool_calls: list[ToolCallRecord]
    final_text: str  # the agent's final message content
    prompt_sha: str  # injected by the overlay (NOT computed in shared code)

    # claude-api overlay populates these; agent-sdk leaves them None.
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
