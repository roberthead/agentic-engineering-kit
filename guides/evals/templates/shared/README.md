# Evals

This directory is the agent eval harness: a small golden dataset plus a hybrid grader that answers *"is the agent good right now?"* against a real model. It is a live, maintained part of the workflow — when you add or expand a tool, or change behavior you care about, add a golden case here.

For the rationale behind every choice below (why hybrid grading, why YAML cases, why this stays out of the pre-PR gate), see `guides/evals/README.md`.

## How to run

```bash
scripts/eval.sh
```

`scripts/eval.sh` makes **real model calls** and spends tokens, so it requires your `ANTHROPIC_API_KEY` and prints a cost warning before running. It is deliberately **not** part of `scripts/validate.sh` — the pre-PR gate stays mocked, fast, and deterministic. Each invocation produces a *fresh* run per case and grades that run; the output is a scored per-case breakdown plus a suite pass/fail, and the script exits non-zero if any case fails.

Because every run is fresh and the model is non-deterministic, a borderline case can pass one run and fail the next on sampling alone. The threshold is a floor over a single sample; if a case is flaky, widen its margin (repeated sampling is intentionally out of scope for this worked example).

## Where golden cases live

Cases are checked-in YAML, one file per case, under `cases/`:

```
cases/
  list_agents_includes_concierge.yaml   # assertion-led
  time_in_tokyo.yaml                     # judge-led
```

One-file-per-case keeps adding a case a clean, conflict-free file-add, and the YAML stays diffable and comment-friendly.

## Adding a case

1. Copy an existing case file in `cases/` to a new `cases/<your_slug>.yaml`.
2. Set `id` to match the filename, write a one-line `description`, and leave `prompt_sha: null` (it is injected at run time — see below).
3. Fill in `input` (what you send the agent) and the `assertions` block.
4. If the case needs quality judgment, add the optional `judge` block; otherwise omit it.

## Assertions vs. judge: the hybrid split

Every case runs **deterministic assertions**; cases that need quality judgment *also* run the **LLM judge**.

- **Assertions** (`assertions:`) are pure checks over the persisted run — no model call, free, deterministic. They confirm structural facts: the run status is `ok`, the expected tool fired (optionally with `args_contains` and `result_contains` matched against its persisted output), and the output shape. This is the floor: it catches wiring and regressions cheaply.
- **Judge** (`judge:`, optional) is a single Claude call that scores the agent's final answer against a rubric (1-5 per item; the case passes when the mean meets `threshold`). Use it for "is the answer correct and coherent?" — judgments assertions can't make. Hand the judge the relevant tool output via `include_tool_results` so it grades against a deterministic anchor, not a guess.

A case with no `judge:` block is assertion-only; a case with one must pass **both** the assertions and the judge.

## `prompt_sha`

Each case ships `prompt_sha: null`; the harness overlay injects the real value at run time (it hashes the active system prompt). It stamps every result with the prompt revision that produced it, so results can be **grouped and compared across prompt revisions** — the whole point of an eval suite over time.

With a single starter prompt there is currently only one sha and nothing to group, so `prompt_sha` looks like it does nothing today. **Do not delete it as dead weight** — it is the attribution key that makes the suite meaningful the moment the prompt has more than one revision.
