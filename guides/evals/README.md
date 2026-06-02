# Evals Guide

How to evaluate agents built with this kit, and the dataset, grader, and where-it-runs decisions made for you.

**This guide applies to all three harnesses, but the substrate differs.** The `agent-sdk` and `claude-api` harnesses evaluate persisted `agent_runs` rows (plus their `tool_calls` and `run_events` children); the `claude-code` harness has no database, so it evaluates the CLI run against `prompt.md` files and scores the Astro artifacts under `app/site/`.

This is the *rationale* half of the evals work — it makes the calls. The `scaffold-eval-harness` story is the worked-example half: it instantiates those decisions into a runnable suite and a `scripts/eval.sh` entry point. Read this for the reasoning, not as a procedure to execute.

A note on tense: the kit is pre-kickstart, so the substrate this guide refers to mostly isn't built yet. `app/server/` holds only kit stubs today — no implementation, no database, no `agent_runs` table; `scripts/eval.sh` doesn't exist at all. Every reference to persisted runs below is a forward-reference to what the `agent-sdk` and `server` guides describe the substrate *will* be once a project is kickstarted, not to live code.

## At a glance

| Concern | Choice |
|---|---|
| Grader strategy | Hybrid — deterministic assertions on run state + LLM-as-judge against a rubric |
| Dataset | Checked-in golden cases that diff cleanly in review, keyed by `prompt_sha` |
| Where it runs | Local / manual, on demand, via a `scripts/eval.sh` entry point (created by the scaffold story) |
| CI / nightly automation | Deferred to a later story |
| Scoring | Judge score (or pass-fraction) vs. a threshold → pass/fail per case and per suite |
| Substrate — SDK / API | Persisted `agent_runs` / `tool_calls` / `run_events` rows |
| Substrate — claude-code | CLI run against `prompt.md`; scored against Astro artifacts in `app/site/` |

## What evals own

Evals answer one question that no other layer can: **is this agent still good?** Concretely, they own:

- **Answer-quality regression detection.** Unit and integration tests can prove the wiring is intact, but they run against a mocked model and so say nothing about whether the agent's actual output got better or worse. Evals are the only thing in the kit that measures output quality over time.
- **Wiring and structure verification on persisted run state.** Did the run finish with status `ok`? Were the expected tool calls made? Does the output match the expected shape (e.g. a JSON schema)? These are cheap, deterministic checks on the same persisted run that the judge also reads.
- **Attributing a regression to a prompt change vs. a code change.** Because cases are grouped by `prompt_sha`, a quality drop can be traced to the prompt revision that caused it rather than guessed at. This is the property that turns "something got worse" into "*this* prompt edit got worse."

## What evals do not own

- **`scripts/validate.sh`.** That is the deterministic correctness gate — linters, type checkers, and the unit/integration suites running against a *mocked* model. Evals are non-deterministic and hit a real model; they are a separate concern with a separate entry point (`scripts/eval.sh`). See *Where evals run*.
- **CI gating.** Whether a regression should block a merge is a real question, but automating evals in CI or nightly is explicitly deferred to a later story. Today they run locally, on demand.
- **Observability and tracing.** OTel spans, structured logs, and the persisted `agent_runs` rows are produced by the harness (see `guides/harnesses/agent-sdk/README.md`). Evals *consume* that persisted run state; they do not produce traces. The relationship is one-directional: instrumentation writes the substrate, evals read it.
- **Prompt engineering itself.** Evals tell you a prompt regressed; they don't tell you how to fix it. Authoring and iterating on prompts is per-project work, not part of this guide.

## The unit of evaluation

The `agent-sdk` guide already names the thing evals operate on: the `agent_runs` row plus its `tool_calls` and `run_events` children is "the unit of evaluation." That row carries everything an eval needs without re-running the model — final status, the ordered tool calls, the recorded events, and the message content.

Critically, every `agent_runs` row persists a `prompt_sha`, and the harness guide is explicit about why: "Evaluations group by `prompt_sha`, not by agent name — that's how you tell whether a regression came from a prompt change or something else." That single decision makes the substrate eval-ready before any eval suite exists: a golden case is pinned to a `prompt_sha`, so when the prompt changes its hash changes and results re-group under the new hash. Attribution falls out of the data model rather than requiring bookkeeping.

That vocabulary — a run row, its tool calls and events, keyed by `prompt_sha` — is the shared foundation the per-harness sections below build on.

## The grader: a hybrid strategy

The core decision: **use two graders, each for what it's good at.**

- **Deterministic assertions** run against the persisted run state. Was the final status `ok`? Were the expected tool calls made, in the expected shape? Does the structured output validate against its JSON schema? These checks are cheap, fast, and fully reproducible — there is exactly one right answer and no model is consulted to find it. They verify *wiring and structure*.
- **LLM-as-judge against a rubric** runs against the message content. Given the case input and the agent's answer, a model scores the answer along a rubric (e.g. correctness, completeness, tone) — typically a 1–5 score or a pass-fraction over rubric items. This is the only practical way to measure *open-ended answer quality*, where "good" is a judgment, not an equality check.

The split is not arbitrary; it **mirrors the kit's existing mocked-vs-live test split.** The `agent-sdk` guide already runs integration tests against a mocked model that "catch wiring regressions," alongside a small set of recorded/live runs that "catch prompt regressions." Evals draw the same line: the assertion grader is the eval-time analog of the mocked test (deterministic, structural), and the judge grader is the analog of the live run (it sees real output and measures quality). A team that already understands why the test suite is split this way understands the grader without new conceptual load.

When does each apply? Run assertions on every case — they are cheap and catch the largest, most embarrassing class of failure (the agent stopped calling a tool, the output stopped parsing). Run the judge on cases whose answer is open-ended enough that no assertion can capture "good." Many cases want both: assertions to confirm the run was structurally sound, then the judge to grade the answer it produced.

## The dataset: golden cases

Evals run against a set of **golden cases** — saved inputs paired with the assertions and rubric that define a passing result. The properties of that dataset are locked here; the exact serialization is not.

- **Checked into the repo.** Cases live in version control alongside the code they evaluate, for the same reason prompts are files rather than strings: they "diff cleanly in code review." A reviewer can see, in a pull request, exactly which case was added, which expected answer changed, and which threshold moved.
- **Diffable in review.** This rules out opaque or binary formats and anything stored outside the repo (see *Alternatives considered* on hosted tooling). A human reading the diff should be able to reason about what the change does to the suite.
- **Keyed by `prompt_sha`.** Each case is labeled so its results group by the prompt revision under test, consistent with the `prompt_sha`-grouping convention the `agent-sdk` guide already establishes. This is what makes a regression attributable rather than merely visible.

**Format and path are a recommendation, not a locked decision.** A reasonable default is a directory of structured files — e.g. `app/evals/cases/` holding `.yaml` (readable, comment-friendly) or `.jsonl` (one case per line, append-friendly, trivially streamable). The `scaffold-eval-harness` story finalizes the format and location. This guide deliberately does not pre-commit either, so the scaffold can choose based on the concrete harness it instantiates.

## Scoring and regression thresholds

Scoring is conceptual here; the shape is:

- **A judge score becomes pass/fail via a threshold.** A rubric produces a number (say a 1–5 score, or the fraction of rubric items satisfied). The suite defines a threshold — e.g. "mean rubric score ≥ 4.0" or "≥ 90% of cases pass" — below which the case or suite is a failure. Set the initial threshold from a known-good baseline run, then treat the threshold as a committed artifact: raising it ratchets quality up, lowering it should be a deliberate, reviewed decision.
- **Read a drop by which grader failed** — the diagnostic payoff of the hybrid split (see *The grader* above). An **assertion failure is a wiring regression**: a tool stopped being called, the status came back non-`ok`, the output stopped validating — a code problem, and the same class the mocked integration tests should have caught, so it usually signals a test-suite gap. A **judge-score drop with assertions still green is a prompt / quality regression**: the run was structurally fine but the answers got worse, pointing at the prompt, not the plumbing.
- **Attribution rides on `prompt_sha` grouping.** Because results group by hash, a judge-score drop is read against the prompt revision that introduced it. "Quality fell when `prompt_sha` changed from X to Y" is a far more actionable signal than an undifferentiated score decline.

## Where evals run

Evals run **locally and manually, on demand, through a `scripts/eval.sh` entry point.** That script does not exist yet — introducing it as the canonical eval entry point (alongside the existing `setup.sh` / `start.sh` / `validate.sh`) is the `scaffold-eval-harness` story's job. This guide names it as the intended interface, nothing more.

CI and nightly automation are **explicitly deferred.** When evals do get automated, it will be a separate, opt-in path — not folded into the per-commit gate.

They do **not** belong in `scripts/validate.sh`, and the reason is the same one the `agent-sdk` guide already gives for keeping live runs out of every CI build: "Avoid running every CI build against a real model. Non-determinism makes failures noisy and erodes trust in the suite." `validate.sh` is the deterministic correctness gate CI uses to decide whether a change can merge — it must be fast, cheap, and repeatable, which a real-model eval is not:

- **Non-determinism** — the same input can score differently across runs, so a green/red gate built on it produces flapping failures.
- **Cost** — every run spends real model tokens; gating every commit multiplies that by the commit rate.
- **Latency** — real-model runs are slow enough to break the tight feedback loop a pre-PR check depends on.

Keep the two cleanly separated: `validate.sh` proves the code is correct against a mocked model; `eval.sh` measures whether the agent is good against a real one. Conflating them degrades both.

## Per-harness substrate

The grader strategy and dataset properties are the same across harnesses. What differs is what the assertions read and what the judge is handed.

### agent-sdk

Evals build directly on the persisted run. Deterministic assertions query the `agent_runs` row and its `tool_calls` / `run_events` children — final status, which tools were invoked and with what arguments, the recorded event sequence, output shape. The judge reads the message content off the same run. Because the run is already persisted, an eval re-grades historical runs without re-invoking the model, and groups everything by the row's `prompt_sha`.

### claude-api

Identical substrate to `agent-sdk` — the same `agent_runs` / `tool_calls` / `run_events` rows — with extra columns to assert on. A custom Claude API harness persists per-call **token and cost** figures and the model's **`stop_reason`**. That gives evals two additional deterministic checks the SDK harness doesn't surface as cleanly: assert that a run didn't blow a token/cost budget, and assert that it stopped for the expected reason (e.g. `end_turn` rather than `max_tokens`, which often signals a truncated, low-quality answer). These ride alongside the same status/tool-call/shape assertions.

### claude-code

No database, so the substrate is different and the treatment here is deliberately light — its scaffold is deferred. There is no `agent_runs` row to query. Instead, evals run the Claude Code CLI against the agent's `prompt.md` files and score the resulting Astro artifacts under `app/site/`. A golden case is an **input prompt plus expected artifact properties** (e.g. the artifact was produced, it has the expected structure, its content satisfies a rubric). The same hybrid split applies in spirit — deterministic checks on the artifact's existence and shape, judge on its content quality — but the mechanics are left to the scaffold story. The stance to carry forward: inputs are prompts, the scored objects are artifacts.

## Alternatives considered

- **Assertion-only.** Drop the judge; grade purely on deterministic checks against run state. Cheap, fully reproducible, and CI-friendly — it would even be safe in `validate.sh`. Rejected as the default because it structurally *cannot* measure answer quality: it verifies the agent called the right tools and produced well-shaped output, but says nothing about whether the answer was actually good. That is the one thing evals exist to measure.
- **LLM-judge-primary.** Lean entirely on the judge and skip the assertions. It measures quality, which is the point — but it is non-deterministic, costs real money per case, and the judge itself is a model that can be wrong. A judge-primary strategy obligates you to validate the judge against expert-labeled examples and track its precision and recall separately, as the `claude-api` guide notes — real work that the hybrid approach lets you adopt incrementally rather than up front. Rejected as the default because the cheap deterministic checks catch the largest failure class for free; throwing them away to rely solely on a costly, fallible grader is a poor trade.
- **Hosted / third-party eval tooling** (e.g. Braintrust, LangSmith, Promptfoo). Fast to adopt and feature-rich — dashboards, run history, judge tooling out of the box. Rejected as the default because it adds an external dependency and, more decisively, pulls eval data *out of the repo*. That breaks the checked-in, diffable-in-review property that makes a golden-case change reviewable in a pull request next to the code it grades. A team that already runs one of these can layer it on, but the kit's default keeps the dataset in version control.

The hybrid default is the synthesis: keep the cheap deterministic assertions (the strength of assertion-only), add the judge only where quality genuinely needs measuring (the strength of judge-primary), and keep the whole dataset checked in and diffable (the property hosted tooling sacrifices).

## References

- `guides/server/README.md` — the README-as-rationale pattern this guide follows, and the persistence layer (SQLAlchemy / Postgres) the run substrate lives in.
- `guides/harnesses/agent-sdk/README.md` — the "unit of evaluation" language (`agent_runs` + `tool_calls` + `run_events`), the `prompt_sha` grouping convention, and the mocked-vs-live test split this guide's grader strategy mirrors.
- `../../user-stories/backlog/scaffold-eval-harness.md` — the worked-example half: instantiates these decisions into a runnable suite, finalizes the dataset format and path, and creates the `scripts/eval.sh` entry point.
