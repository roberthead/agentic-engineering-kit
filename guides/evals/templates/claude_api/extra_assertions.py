"""Claude-API overlay: optional extra assertions over the run contract.

This file ships ONLY with the `claude-api` harness overlay. The shared
`assertions.py` is harness-agnostic and deliberately does NOT contain these
checks, because they read contract fields (`stop_reason`, token counts, cost)
that only the claude-api overlay's `produce_run.py` populates — the agent-sdk
overlay leaves them `None` and ships no `extra_assertions.py` at all.

The shared `runner.py` detects this file by *presence* (not by catching an
import error), so the agent-sdk suite — which ships no `extra_assertions.py` —
simply finds no extras to call, while a present-but-broken file raises loudly
instead of being silently skipped:

    if importlib.util.find_spec(".extra_assertions", __package__) is not None:
        extra_module = importlib.import_module(".extra_assertions", __package__)
        assertions = assertions + extra_module.extra_assertions(run)

The shared `assertions.py` is never branched or monkeypatched. When present,
the runner concatenates these results onto the base assertion results before
scoring.

Like the rest of the overlay, this is INERT in the kit repo and excluded from
any kit-level lint/type gate; the cost ceiling is a `# TODO(kickstart)` knob.
"""

from __future__ import annotations

from .models import AssertionResult
from .run_contract import RunRecord

# Per-run cost ceiling, in USD. A single eval case should not cost more than
# this; exceeding it usually means a runaway loop or an unexpectedly long
# answer, which is worth flagging even if the answer is otherwise fine.
#
# TODO(kickstart): set this from the project's `Settings` (the claude-api
# guide keeps a per-model pricing dict and an `AGENT_MAX_COST_USD` ceiling in
# Settings — reuse or derive from those rather than hard-coding here).
_COST_CEILING_USD = 0.05


def extra_assertions(run: RunRecord) -> list[AssertionResult]:
    """Overlay-only checks on claude-api-specific contract fields."""
    return [
        _check_stop_reason(run),
        _check_cost_budget(run),
    ]


def _check_stop_reason(run: RunRecord) -> AssertionResult:
    """A clean turn ends with `end_turn`.

    Any other terminal reason (notably `max_tokens`) signals a likely truncated
    or low-quality answer: the model ran out of room rather than deciding it was
    done. Treat a missing `stop_reason` as a failure too — this overlay is
    supposed to populate it, so `None` means the run was not mapped correctly.
    """
    passed = run.stop_reason == "end_turn"
    if run.stop_reason is None:
        detail = "stop_reason is None (claude-api overlay should populate it)"
    elif passed:
        detail = "stop_reason == 'end_turn'"
    else:
        detail = (
            f"stop_reason == {run.stop_reason!r} "
            "(likely truncated / low-quality; expected 'end_turn')"
        )
    return AssertionResult(name="stop_reason_end_turn", passed=passed, detail=detail)


def _check_cost_budget(run: RunRecord) -> AssertionResult:
    """A single run should stay under the per-run cost ceiling."""
    if run.cost_usd is None:
        return AssertionResult(
            name="cost_budget",
            passed=False,
            detail="cost_usd is None (claude-api overlay should populate it)",
        )
    passed = run.cost_usd <= _COST_CEILING_USD
    detail = (
        f"cost_usd={run.cost_usd:.4f} "
        f"{'<=' if passed else '>'} ceiling={_COST_CEILING_USD:.4f}"
    )
    return AssertionResult(name="cost_budget", passed=passed, detail=detail)
