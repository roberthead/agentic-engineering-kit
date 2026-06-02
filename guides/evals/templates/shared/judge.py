"""The LLM-as-judge grader: a single Claude call against a rubric.

``judge_case`` returns ``None`` for assertion-only cases (no ``judge:`` block).
Otherwise it builds a judge prompt from the case input, the run's ``final_text``,
and the outputs of the tool calls named in ``case.judge.include_tool_results``,
then makes ONE Claude call asking for a 1-5 score per rubric item plus a one-line
rationale. The case passes when ``mean(scores) >= threshold``.

This is a worked example, not a judge framework: the prompt is a short inline
constant and the parsing is intentionally simple. Harden it per project if the
judge becomes load-bearing.
"""

import json
import statistics

from .models import GoldenCase, JudgeResult
from .run_contract import RunRecord

# A short inline judge prompt. Keep it small — this is a worked example.
JUDGE_SYSTEM = (
    "You are a strict grader for an AI agent's answer. You are given the user's "
    "request, the agent's final answer, any relevant tool results, and a rubric. "
    "Score each rubric item from 1 (fails) to 5 (fully satisfies). Respond with "
    "ONLY a JSON object of the form "
    '{"scores": [<int per rubric item, in order>], "rationale": "<one line>"}.'
)


def judge_case(case: GoldenCase, run: RunRecord) -> JudgeResult | None:
    if case.judge is None:
        return None
    spec = case.judge

    # Splice in the named tool results so the judge grades against the
    # deterministic tool output, not its own guess.
    wanted = set(spec.include_tool_results)
    tool_results = [
        f"- {call.name}: {call.output}"
        for call in run.tool_calls
        if call.name in wanted
    ]
    rubric_block = "\n".join(
        f"{i + 1}. {item}" for i, item in enumerate(spec.rubric)
    )
    tool_results_block = "\n".join(tool_results) or "(none)"
    user_prompt = (
        f"User request:\n{case.input.content}\n\n"
        f"Agent final answer:\n{run.final_text}\n\n"
        f"Relevant tool results:\n{tool_results_block}\n\n"
        f"Rubric (score each 1-5, in order):\n{rubric_block}"
    )

    # TODO(kickstart): get Anthropic client + cheap judge model from
    # app.server config (no os.environ here). The judge model is a cheap model
    # by default; that choice is a kickstart-time cost knob. Path matches the
    # server guide's src/ layout (same root the overlays import from).
    from app.server.src.config import get_settings  # type: ignore[import-not-found]

    settings = get_settings()
    client = settings.anthropic_client
    judge_model = settings.eval_judge_model

    response = client.messages.create(
        model=judge_model,
        max_tokens=512,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # A malformed judge response must fail ONE case, not crash the whole suite,
    # so parsing is defensive: a fenced/non-JSON body, a missing "scores" key, a
    # non-text content block, or a rubric-length mismatch all become a failed
    # JudgeResult with a readable rationale.
    try:
        text = response.content[0].text
        payload = json.loads(text)
        scores = [float(score) for score in payload["scores"]]
        if len(scores) != len(spec.rubric):
            raise ValueError(
                f"judge returned {len(scores)} scores for "
                f"{len(spec.rubric)} rubric items"
            )
        rationale = str(payload.get("rationale", ""))
    except (json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError, IndexError) as exc:
        return JudgeResult(
            score=0.0,
            threshold=spec.threshold,
            passed=False,
            rationale=f"judge response unparseable: {exc}",
        )

    mean_score = statistics.fmean(scores) if scores else 0.0
    return JudgeResult(
        score=mean_score,
        threshold=spec.threshold,
        passed=mean_score >= spec.threshold,
        rationale=rationale,
    )
