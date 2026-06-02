"""The eval orchestrator and reporter.

For each golden case the runner: produces a fresh ``RunRecord`` via the harness
overlay's ``produce_run``, runs the harness-agnostic base assertions, runs the
overlay's ``extra_assertions`` if one was copied in, runs the judge, builds a
``CaseResult``, and finally aggregates a ``SuiteResult``, prints a readable
summary, and exits non-zero if the suite failed.

Printing + exit code are intentionally the runner's terminal step — there is no
separate ``report.py``.

Run it as: ``python -m <import-root>.evals.runner`` (the kickstart step resolves
the exact module path for the project's configured ``src/`` import root).
"""

import importlib
import importlib.util
import sys
from pathlib import Path

from .assertions import run_assertions
from .judge import judge_case
from .loader import load_cases
from .models import AssertionResult, CaseResult, GoldenCase, SuiteResult

# produce_run.py arrives via the harness overlay copy at kickstart
# (agent_sdk/ or claude_api/). It is not part of shared/.
from .produce_run import produce_run  # type: ignore[import-not-found]

CASES_DIR = Path(__file__).parent / "cases"


def _grade_case(case: GoldenCase) -> CaseResult:
    run = produce_run(case)

    assertions: list[AssertionResult] = run_assertions(case, run)

    # The claude-api overlay ships extra_assertions.py (stop_reason / token /
    # cost checks); agent-sdk does not. Detect *presence* with find_spec rather
    # than catching ImportError on the import itself — otherwise a real import
    # error inside a present extra_assertions.py (e.g. a bad transitive import)
    # would be silently swallowed and its checks would vanish with the suite
    # still reporting PASS. find_spec returns None only when the module is
    # genuinely absent (agent-sdk); a present-but-broken module raises loudly.
    if importlib.util.find_spec(".extra_assertions", __package__) is not None:
        extra_module = importlib.import_module(".extra_assertions", __package__)
        assertions = assertions + extra_module.extra_assertions(run)

    judge = judge_case(case, run)

    passed = all(result.passed for result in assertions) and (
        judge is None or judge.passed
    )
    return CaseResult(
        case_id=case.id,
        assertions=assertions,
        judge=judge,
        passed=passed,
    )


def _print_case(result: CaseResult) -> None:
    mark = "PASS" if result.passed else "FAIL"
    print(f"[{mark}] {result.case_id}")
    for assertion in result.assertions:
        sub = "ok" if assertion.passed else "XX"
        print(f"    ({sub}) {assertion.name}: {assertion.detail}")
    if result.judge is not None:
        judge = result.judge
        sub = "ok" if judge.passed else "XX"
        print(
            f"    ({sub}) judge: score={judge.score:.2f} "
            f"threshold={judge.threshold:.2f} — {judge.rationale}"
        )


def main() -> None:
    cases = load_cases(CASES_DIR)
    results = [_grade_case(case) for case in cases]
    suite = SuiteResult(
        results=results,
        passed=all(result.passed for result in results),
    )

    print("=== eval results ===")
    for result in results:
        _print_case(result)

    passed_count = sum(1 for result in results if result.passed)
    suite_mark = "PASS" if suite.passed else "FAIL"
    print(
        f"=== suite: {suite_mark} "
        f"({passed_count}/{len(results)} cases passed) ==="
    )

    if not suite.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
