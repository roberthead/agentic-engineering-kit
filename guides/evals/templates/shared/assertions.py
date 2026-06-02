"""The deterministic grader: pure, no model call, harness-agnostic.

``run_assertions`` reads a ``RunRecord`` (the documented run contract) and the
``GoldenCase`` and returns one ``AssertionResult`` per check. It consults no
model and touches no app state, so it is fully reproducible and identical across
both harnesses.

This module is NEVER edited by an overlay. The ``claude-api`` overlay's extra
checks (stop_reason, token/cost budget) live in a sibling ``extra_assertions.py``
that the runner concatenates — so this file stays the same byte-for-byte across
harnesses and is never branched or monkeypatched.
"""

from .models import AssertionResult, GoldenCase, ToolCallAssertion
from .run_contract import RunRecord, ToolCallRecord


def run_assertions(case: GoldenCase, run: RunRecord) -> list[AssertionResult]:
    results: list[AssertionResult] = []
    spec = case.assertions

    # 1. Final status.
    status_ok = run.status == spec.status
    results.append(
        AssertionResult(
            name="status",
            passed=status_ok,
            detail=f"expected status {spec.status!r}, got {run.status!r}",
        )
    )

    # 2. Expected tool calls — each must have a matching entry in run.tool_calls.
    for expected in spec.tool_calls:
        results.append(_check_tool_call(expected, run.tool_calls))

    # 3. Output shape.
    results.append(_check_output_shape(spec.output_shape, run.final_text))

    return results


def _check_tool_call(
    expected: ToolCallAssertion, calls: list[ToolCallRecord]
) -> AssertionResult:
    name = f"tool_call:{expected.name}"
    candidates = [call for call in calls if call.name == expected.name]
    if not candidates:
        return AssertionResult(
            name=name,
            passed=False,
            detail=f"no tool call named {expected.name!r} in run",
        )

    # A call matches if args_contains is a subset of its input AND
    # (if set) result_contains is a substring of its output.
    for call in candidates:
        if not _is_subset(expected.args_contains, call.input):
            continue
        if (
            expected.result_contains is not None
            and expected.result_contains not in call.output
        ):
            continue
        return AssertionResult(
            name=name,
            passed=True,
            detail=f"matched call to {expected.name!r}",
        )

    return AssertionResult(
        name=name,
        passed=False,
        detail=(
            f"{expected.name!r} was called, but none matched "
            f"args_contains={expected.args_contains!r} "
            f"result_contains={expected.result_contains!r}"
        ),
    )


def _check_output_shape(output_shape: str, final_text: str) -> AssertionResult:
    name = f"output_shape:{output_shape}"
    if output_shape == "non_empty_text":
        passed = bool(final_text.strip())
        return AssertionResult(
            name=name,
            passed=passed,
            detail="final_text is non-empty" if passed else "final_text is empty",
        )
    # `json_schema: <path>` is a documented extension point; unknown shapes fail
    # loudly rather than silently passing.
    return AssertionResult(
        name=name,
        passed=False,
        detail=f"unknown output_shape {output_shape!r}",
    )


def _is_subset(expected: dict[str, object], actual: dict[str, object]) -> bool:
    """True if every top-level key/value in ``expected`` equals ``actual``'s.

    Top-level only: values are compared by equality, so a nested-dict value
    must match exactly rather than as a recursive sub-subset. That is enough
    for the flat tool args in the worked example; extend here if a case needs
    nested containment.
    """
    return all(actual.get(key) == value for key, value in expected.items())
