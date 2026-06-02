# Story: Scaffold Eval Harness During Kickstart

## Summary

AS a developer who just kickstarted an `agent-sdk` or `claude-api` project

I WANT a minimal eval harness generated for me — a tiny golden dataset, a hybrid grader, and a `scripts/eval.sh` entry point

SO THAT "grow the loop when evals demand it" is actionable from day one instead of a greenfield I have to design from scratch.

## Context

The companion to `add-evals-guide`. The guide *decides*; this story *instantiates* those decisions as a worked example, the same way the concierge's two MVP tools "double as worked examples of how this harness defines tools and as a smoke test that tool wiring works end-to-end" (KICKSTART.md).

Scope is deliberately the two harnesses that share a substrate: `agent-sdk` and `claude-api` both persist `agent_runs`/`tool_calls`/`run_events` and a `prompt_sha`, so evals build directly on persisted runs. `claude-code` has no DB and needs a fundamentally different scaffold (run the CLI against `prompt.md`, score Astro artifacts) — **deferred to its own follow-up story.**

Depends on `add-evals-guide` — don't build the scaffold before the guide has fixed the dataset format, grader strategy, and thresholds.

## Acceptance Criteria

- KICKSTART's playbook generates an eval scaffold for the `agent-sdk` and `claude-api` harnesses (and only those two for now).
- The scaffold is **minimal and worked-example-sized**, not a heavy framework: a handful of golden cases tied to the *existing* concierge's two read-only MVP tools — not speculative domain cases that don't exist on a fresh kickstart.
- Golden dataset lands in the format/location the guide specifies (checked-in, diffable, keyed). At least one case exercises the deterministic-assertion path and at least one exercises the LLM-judge path.
- A **hybrid grader** is scaffolded: deterministic assertions on persisted run state (status, tool calls made, output shape) + an LLM-as-judge scorer with a rubric, matching the guide's default.
- A `scripts/eval.sh` entry point exists, following the repo's script conventions (`#!/usr/bin/env bash`, `set -euo pipefail`, `cd "$(dirname "${BASH_SOURCE[0]}")/.."`, step banners, non-zero exit on failure). It runs the eval on demand locally.
- The scaffold respects the mocked-vs-live split: `scripts/eval.sh` makes real-model calls and is **not** wired into `scripts/validate.sh` (the pre-PR gate stays deterministic and free). The eval slots alongside the existing `RUN_LIVE=1` recorded-runs pattern rather than duplicating it.
- A new contributor can run `scripts/eval.sh`, see scored output for the concierge, and understand where to add their own golden cases (a short README or header comment pointing back to `guides/evals/README.md`).
- KICKSTART.md and the relevant `app/server/CLAUDE.md` are updated so the eval scaffold and `scripts/eval.sh` are documented as live, maintained parts of the workflow.

## Notes

- **Pre-kickstart framing (locked with user):** the kit has no live app — no `app/server/` implementation, no DB, no test runner, no `scripts/` dir. So this story does **not** produce a runnable eval suite in *this* repo. It produces (a) **copyable template files** committed under a templates path, which the kickstart playbook copies into `app/` when a real project is created, plus (b) the **KICKSTART/guide instructions** that perform that copy and wire it up. The templates are reference-only and inert until kickstart instantiates them. Read every acceptance-criterion verb ("exists", "runs", "a contributor can run") as "the template, once copied by kickstart, does this" — not "this executes in the kit repo today."
- **Template delivery (locked with user):** copyable template files (not inline code blocks in prose), so they stay lintable/reviewable as real code even while inert. Planner to recommend the exact templates path/layout.
- Decisions already made with the user: hybrid grader; local/manual `scripts/eval.sh` (no CI wiring); `agent-sdk` + `claude-api` first.
- **Deferred follow-up:** a `claude-code` eval scaffold (CLI-against-prompts, score artifacts). Worth its own backlog story once this lands and the guide's claude-code section is validated against a real attempt.
- Watch the tension the user flagged: don't over-scaffold. The day-one app has only the concierge + two tools; the eval should be small enough to read in one sitting and obviously extensible, mirroring the kit's minimalism ("default to the smallest loop... grow it only when evals demand it").
- `scripts/eval.sh` becomes a fourth canonical script. The CLAUDE.md `scripts/` section currently enumerates exactly three (setup/start/validate) and says "Create all three during kickstart" — reconcile that wording if eval becomes a standard fourth entry point, or keep eval harness-conditional and say so.

## Implementation Plan

### Overview

Ship the worked-example half of the evals work as **copyable template files** under `guides/evals/templates/` (co-located with the rationale guide), plus the `KICKSTART.md` / root-`CLAUDE.md` edits that copy them into the server's source tree and wire up `scripts/eval.sh` at kickstart. Nothing runs in the kit repo today; every template is real, lintable Python/bash that is inert until kickstart instantiates it. The dataset is **YAML golden cases** at `app/server/src/evals/cases/`, graded by a **hybrid grader** (deterministic assertions + LLM-judge) that reads a documented **persisted-run contract** (so it doesn't depend on column names the claude-api guide hasn't pinned), driven by a manual `scripts/eval.sh` that hits a real model and is deliberately kept out of `scripts/validate.sh`.

### 1. Templates path + directory layout

**Decision (locked with user): templates live under `guides/evals/templates/`**, co-located with the rationale guide they instantiate. Rationale for this placement: all eval material — the *why* (`guides/evals/README.md`) and the *worked example* (`guides/evals/templates/`) — sits in one place, so a reader who finds the guide finds the templates next to it. The deferred `claude-code` scaffold gets an obvious home at `guides/evals/templates/claude-code/` without a later move.

- **Copy target follows the server guide's `src/` layout.** The server guide places code under `app/server/src/`, so the eval package lands at `app/server/src/evals/` (NOT a top-level `app/server/evals/`), and `eval.sh` invokes it through the project's configured import root. KICKSTART copies `guides/evals/templates/shared/` + the chosen overlay into `app/server/src/evals/`, and `guides/evals/templates/eval.sh` → `scripts/eval.sh`.
- **Template dir names use underscores because they become Python packages** (`agent_sdk/`, `claude_api/`); they map to the hyphenated harness names (`agent-sdk`, `claude-api`). KICKSTART must translate: for the `agent-sdk` harness, `cp -R guides/evals/templates/agent_sdk/* app/server/src/evals/` (the overlay merges *onto* the already-copied `shared/` — there is no filename collision; the only overlay file is `produce_run.py` plus, for claude-api, `extra_assertions.py`). §6 spells out the exact per-harness commands.
- The templates under `guides/evals/templates/` are reference-only and import app modules that don't exist pre-kickstart, so they must be excluded from any kit-level lint/type gate. Add a `guides/evals/templates/README.md` stating this, **and pre-declare the exclusion** today in standalone kit-root config (a `ruff.toml` with `extend-exclude = ["guides/evals/templates"]`, and a minimal `mypy.ini` with the equivalent `exclude` regex — standalone files, since the kit has no `pyproject.toml` and installs no Python tooling yet) so the carve-out exists before the gate that needs it, rather than a promissory note that gets lost. The load-bearing record also goes in root `CLAUDE.md` (see §6).

Proposed tree (each file one-line purpose):

```
guides/evals/
  README.md                          # (existing) the rationale guide
  templates/
    README.md                        # what these templates are; copied into app/server/src/ at kickstart, inert until then
    eval.sh                          # -> scripts/eval.sh : the entry point (shared, both harnesses)
    shared/                          # -> app/server/src/evals/  (harness-agnostic core)
      __init__.py
      README.md                      # contributor doc (written for its post-copy app/ home): how to run, where to add cases; points to guides/evals/README.md
      run_contract.py                # the persisted-run interface the graders read (status, ordered tool_calls{name,input,output}, final_text; claude-api adds stop_reason/tokens/cost)
      models.py                      # Pydantic: GoldenCase, AssertionSpec, RubricSpec, AssertionResult, JudgeResult, CaseResult, SuiteResult
      loader.py                      # load + validate YAML cases; prompt_sha is INJECTED by the overlay, not computed here
      assertions.py                  # deterministic grader over the run contract (harness-agnostic; never edited by overlays)
      judge.py                       # LLM-as-judge grader (rubric -> 1-5 score -> pass/fail); kickstart seam for client/model
      runner.py                      # orchestrates: load -> produce run -> grade -> print scored output -> exit code
      cases/
        time_in_tokyo.yaml           # judge-led case (get_current_time + coherent spoken answer)
        list_agents_includes_concierge.yaml  # assertion-led case (tool called + result_contains)
    agent_sdk/                       # overlay -> app/server/src/evals/ : SDK-specific run production
      produce_run.py                 # invokes the SDK via app's agent_runner; supplies the run-contract object + prompt_sha
    claude_api/                      # overlay -> app/server/src/evals/ : API-specific run production
      produce_run.py                 # drives the hand-rolled loop; supplies the run-contract object + prompt_sha
      extra_assertions.py            # optional extra_assertions(run) -> list[AssertionResult]: stop_reason/token/cost checks
    (claude-code/ reserved for the deferred follow-up story)
```

`report.py` is intentionally **folded into `runner.py`** (printing + exit code is the runner's terminal step) to hold the minimalism line — five shared modules, not six.

### 2. Dataset format decision

**Chosen serialization: YAML, one file per case, at `app/server/src/evals/cases/*.yaml`** (finalizing the guide's deferred `app/evals/cases/` + `.yaml`/`.jsonl` float). Rationale:

- **Diffability + comments win over `.jsonl`.** A rubric and assertion set benefit from inline comments explaining *why* a threshold is what it is; JSONL forbids comments and crams a case onto one line, which diffs poorly when a multi-line rubric changes. One-file-per-case (vs. one multi-doc YAML) means adding a case is a pure file-add — the cleanest possible PR diff, and no merge conflicts on a shared file.
- **`.py` rejected** for cases: it makes the dataset code, not data; loses the "a non-engineer can read/add a case" property and invites logic creep into what should be declarative fixtures.
- **Path under `app/server/src/`** (following the server guide's layout, not a repo-root `app/evals/`) because the loader, graders, and the runs being graded are all server-side Python sharing the server's `uv` env, models, and Postgres connection. Co-locating in the source tree keeps imports and the `uv run python -m` invocation correct.

**Shape of a single golden case (fields):**

```yaml
id: time_in_tokyo                 # stable, filename-matching slug
description: ...                  # one line, human-facing
prompt_sha: null                  # injected at run time by the overlay; key for cross-revision grouping
input:
  kind: chat
  content: "What time is it in Tokyo?"
assertions:                       # deterministic, run on every case
  status: ok
  tool_calls:
    - name: get_current_time      # was this tool invoked...
      args_contains: { timezone: "Asia/Tokyo" }   # ...with these args...
      result_contains: ":"        # ...and did its persisted RESULT contain this? (omit to skip)
  output_shape: non_empty_text    # only mechanism shipped; `# or: json_schema: <path>` is a documented extension point
judge:                            # optional; present => run the LLM-judge path
  include_tool_results: [get_current_time]   # which tool outputs to splice into the judge prompt
  rubric:
    - "States a time that matches the get_current_time tool result"
    - "Answer is coherent and directly addresses the Tokyo time question"
  threshold: 4.0                  # mean rubric score (1-5) >= threshold to pass
```

Two schema additions came out of plan review: **`tool_calls[].result_contains`** (so an assertion can check the tool's persisted *output*, not just that it fired) and **`judge.include_tool_results`** (so the judge is deterministically handed the right tool result to grade against, instead of guessing). Both are optional.

**Two concrete concierge cases:**

- **Assertion-led — `list_agents_includes_concierge.yaml`**: input "Which agents are available?"; assert `status: ok`, a `list_agents` tool call fired, and `result_contains: concierge` on that call's persisted output. No `judge:` block. A YAML comment notes this is a **wiring-level floor** (day one the roster is just `[concierge]`, so the check is near-tautological) that grows in value as the roster grows — mirroring `KICKSTART.md`'s framing of `list_agents`.
- **Judge-led — `time_in_tokyo.yaml`** (above): assertions confirm `get_current_time(timezone="Asia/Tokyo")` fired and status is `ok` (structural floor), then the judge — handed the `get_current_time` result via `include_tool_results` — grades whether the spoken answer is correct and coherent. This anchors quality measurement on a deterministic tool result, so it stays robust even though the system prompt is bespoke per project.

### 3. Grader design

Worked-example-minimal. The graders read a **documented run contract** (`run_contract.py`), not raw columns — this is what lets the same shared graders serve both harnesses and keeps them off column names the claude-api guide hasn't pinned:

```python
# run_contract.py — what produce_run.py returns; what the graders consume
class ToolCallRecord(BaseModel): name: str; input: dict; output: str   # overlay's produce_run.py coerces the tool result to its serialized string form; result_contains / include_tool_results match against that
class RunRecord(BaseModel):
    status: str                     # "ok" / error
    tool_calls: list[ToolCallRecord]
    final_text: str                 # the agent's final message content
    prompt_sha: str                 # injected by the overlay
    # claude-api overlay populates these; agent-sdk leaves them None:
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
```

```python
# models.py
class GoldenCase(BaseModel):        # parsed from YAML
    id: str; description: str; prompt_sha: str | None
    input: CaseInput
    assertions: AssertionSpec
    judge: RubricSpec | None = None
class AssertionResult(BaseModel): name: str; passed: bool; detail: str
class JudgeResult(BaseModel): score: float; threshold: float; passed: bool; rationale: str
class CaseResult(BaseModel):
    case_id: str; assertions: list[AssertionResult]; judge: JudgeResult | None
    passed: bool                    # all assertions pass AND (judge is None or judge.passed)
class SuiteResult(BaseModel): results: list[CaseResult]; passed: bool
```

- **`assertions.py`** — pure, no model call, **harness-agnostic and never edited by an overlay**. Reads a `RunRecord` and checks: `status == ok`; each expected tool call present with matching `args_contains` (subset) and optional `result_contains`; `output_shape` (non-empty text). Returns `list[AssertionResult]`.
- **`claude_api/extra_assertions.py`** — the overlay's `extra_assertions(run: RunRecord) -> list[AssertionResult]` adds `stop_reason == end_turn` and a per-run token/cost-budget check (the contract fields only claude-api populates). `runner.py` calls `extra_assertions` *if the overlay provides it* and concatenates the results — so the shared `assertions.py` is never branched or monkeypatched.
- **`judge.py`** — single Claude call. Hands the judge the case input, the run's `final_text`, and the tool results named by `include_tool_results`, plus the rubric; asks for a 1-5 score per rubric item + one-line rationale; returns `JudgeResult` where `passed = mean(scores) >= threshold`. **Kickstart seam:** the Anthropic client + judge model name come from the app's `Settings`/config (per the server guide's "no `os.environ` outside config" rule), marked `# TODO(kickstart)`. Keep the judge prompt a short inline constant — a worked example, not a judge framework.
- **Scoring -> pass/fail**: `CaseResult.passed` = all assertions (base + any overlay extras) green AND (no judge OR judge passed). `runner.py` aggregates `SuiteResult`, prints the scored per-case + suite output, and sets the process exit code (no separate `report.py`).

### 4. `scripts/eval.sh`

End-to-end, following repo script conventions (`#!/usr/bin/env bash`, `set -euo pipefail`, `cd "$(dirname "${BASH_SOURCE[0]}")/.."`, a `=== step ===` banner before **each** of the four steps, non-zero exit on failure). `eval.sh` extends the script conventions with a **credential + cost guard** the other three scripts don't need — note that as the reason its shape differs:

1. Banner + guard: require the Anthropic API key env var (fail fast if absent); print that this hits a **real model** and spends tokens.
2. Banner + `uv run python -m <import-root>.evals.runner` — invoked through the project's configured import root (the server guide's `src/` layout; the kickstart step resolves the exact module path). The runner loads YAML cases and **produces a fresh `RunRecord` per case** via the harness overlay's `produce_run.py` (SDK invocation for agent-sdk; hand-rolled loop for claude-api).
3. Banner + grade each run (base assertions + any overlay `extra_assertions` + judge), build and print the scored per-case + suite `SuiteResult`.
4. Banner + exit non-zero if `SuiteResult.passed` is false.

**Fresh-run-per-invocation is deliberate — note its consequences.** Every `eval.sh` run generates new model output and grades *that* (it does not replay frozen runs); this is the right model for "is the agent good *now*?" and matches the guide's "judge sees real output" stance. Document the two consequences so the first contributor isn't surprised: (a) a case can pass one run and fail the next from sampling alone — the threshold is a floor over a single sample by default; flaky cases want a wider margin or repeated sampling (explicitly out of scope for the worked example); (b) each invocation costs tokens × N cases × one judge call each — hence the cost guard and the cheap-judge-model default.

**Relationship to `RUN_LIVE=1` recorded tests / staying out of `validate.sh`:** `eval.sh` is a sibling of the existing `tests/integration/agents/recorded/` live path, not a duplicate — recorded tests answer "did the prompt regress?" via pytest assertions on a real run; evals answer "is the agent good?" via the judge against a rubric, on the same persisted-run substrate. `eval.sh` is **never** called from `validate.sh` (which stays mocked, fast, deterministic). On the gate: **invoking `eval.sh` *is* the gate** — it requires the API key and prints the cost warning, so it must NOT also require the caller to pre-set `RUN_LIVE=1` (that would be user-hostile for a script whose whole purpose is the live run). For consistency with any shared helper that checks the recorded-tests env, `eval.sh` may *export* `RUN_LIVE=1` itself.

### 5. Shared vs. harness-specific

- **Shared (copied for both):** `eval.sh`, `run_contract.py`, `models.py`, `loader.py`, `assertions.py` (base checks, never overlay-edited), `judge.py`, `runner.py`, `cases/*.yaml`, `README.md`. The dataset, grader, scoring, and entry point are substrate-agnostic — they consume a `RunRecord`, not raw rows.
- **Forks (copy exactly one overlay):**
  - `produce_run.py` — *how a run is produced and mapped to a `RunRecord`*. agent-sdk invokes the SDK via the app's `agent_runner`; claude-api drives the hand-rolled loop. **The overlay also supplies `prompt_sha`** (agent-sdk hashes the concierge `prompt.md`; claude-api computes it from its block-list prompt) — the shared `loader.py` does NOT compute the sha, it receives the injected value. This is the right seam because the sha source is genuinely harness-divergent.
  - `claude_api/extra_assertions.py` — only claude-api ships this; agent-sdk has no extra-assertions file, so `runner.py` simply finds none to call. Keeps the shared `assertions.py` identical across both.

### 6. Playbook / instruction edits

- **Root `CLAUDE.md` — add the `guides/` carve-out (load-bearing).** The Filename-conventions/Layout sections define `guides/` as rationale prose. Amend the existing `guides/evals/` Layout bullet (line ~32) to note the one exception, so the agent that reads root `CLAUDE.md` eagerly forms the right model and doesn't try to "fix" the app-importing template Python: e.g. _"`guides/evals/templates/` is the deliberate exception to the 'guides/ is rationale' rule — it holds **inert, copyable template code** (Python/bash/YAML) that kickstart copies into `app/server/src/` and `scripts/`. It is reference code, not live code: it imports app modules that don't exist pre-kickstart and is excluded from any kit-level lint/type gate."_ A leaf README alone is insufficient — the convention-forming file must carry it.
- **Root `CLAUDE.md`, `scripts/` section** — reconcile the "exactly three" wording at BOTH the headline and the detail. Soften the bold line-50 imperative from "**Create all three during kickstart**" to "Create the three universal scripts during kickstart (plus `scripts/eval.sh` on the `agent-sdk`/`claude-api` harnesses — see below)", so the headline agrees with the fourth-script detail. Keep `setup.sh`/`start.sh`/`validate.sh` as the universal three; add a one-line `scripts/eval.sh` bullet scoped "agent-sdk / claude-api only," noting it's created from `guides/evals/templates/`, hits a real model, and is deliberately not run by `validate.sh` (see `guides/evals/README.md`).
- **`KICKSTART.md` Phase 2** — change "creating the three entry-point scripts under `scripts/`" to "creating the entry-point scripts under `scripts/` (the universal three; plus `scripts/eval.sh` for `agent-sdk`/`claude-api`)". Add a short **"Eval scaffold"** step (gated to those two harnesses) with the **explicit per-harness copy commands** (translating the hyphenated harness name to the underscored template dir):
  - `cp -R guides/evals/templates/shared/* app/server/src/evals/`
  - then the matching overlay — `agent-sdk`: `cp -R guides/evals/templates/agent_sdk/* app/server/src/evals/`; `claude-api`: `cp -R guides/evals/templates/claude_api/* app/server/src/evals/`
  - `cp guides/evals/templates/eval.sh scripts/eval.sh`
  - resolve the `# TODO(kickstart)` seams (`produce_run.py` wiring to the concierge runner; `judge.py` client/model from `Settings`; `prompt_sha` source), then **run `scripts/eval.sh` once and confirm scored output** as a *named, non-skippable* checklist item — this is the ONLY place acceptance criterion 7's "see scored output" is ever demonstrated.
  - Note the cases target the concierge's two fixed tools and that the judge case anchors on the deterministic tool result so it survives a bespoke system prompt.
- **`app/server/CLAUDE.md`** (the stub, fleshed out at kickstart) — document `app/server/src/evals/` as a live, maintained part of the workflow: what the dataset is and where cases live, that `scripts/eval.sh` runs them against a real model, that evals are **not** part of `validate.sh`, and the rule "add a golden case when you add/expand a tool or change behavior you care about." Point to `guides/evals/README.md` for rationale.
- **`guides/evals/README.md` cross-ref** — its References section currently points to `../../user-stories/backlog/scaffold-eval-harness.md`; this story has moved to `current/` and will land in `done/`. Update that path when this story finishes (bookkeeping).
- **Markdown convention** — every README/`CLAUDE.md` this story creates or edits must keep a blank line before AND after each header (global repo rule).

### 7. Decisions locked (resolved with user)

- **Templates location:** `guides/evals/templates/` (co-located with the rationale guide), not a top-level `templates/`. KICKSTART copies from there. §1 and §6 reflect this.
- **Eval code location:** copied into `app/server/src/evals/`, following the server guide's `src/` layout (not a top-level `app/server/evals/`); `eval.sh` invokes it through the project's import root. (Resolved in plan review.)
- **claude-api substrate:** the graders read a documented **run contract** (`run_contract.py` → `RunRecord`), not pinned claude-api columns. The claude-api overlay maps its hand-rolled loop's output into that contract and adds `extra_assertions.py`. This avoids front-running the still-"planning-sketch" claude-api guide. (Resolved in plan review.)
- **Dataset format:** YAML, one file per case, at `app/server/src/evals/cases/*.yaml`. (As §2.)
- **No dry-run mode.** Acceptance criterion 7's "see scored output" is **template-only — verified at kickstart** (a named, non-skippable KICKSTART step, §6), not demonstrated in the kit repo. The runner ships no `RUN_LIVE`-off stub path; it stays lean. Review confirms wiring by reading, not running.
- **`# TODO(kickstart)` seams** (named in review): `produce_run.py` (wire to the concierge runner; supply the `RunRecord` + `prompt_sha`) and `judge.py` (Anthropic client + judge model from `Settings`). `models.py`/`loader.py`/`assertions.py`/`run_contract.py` are import-clean and self-contained.
- **`prompt_sha`:** cases ship `prompt_sha: null`; the **overlay** injects it at run time (agent-sdk hashes `prompt.md`; claude-api computes from its block prompt). The shared loader does not compute it. Loader fills `null` → injected sha and leaves verify-against-a-pinned-sha as a documented `# TODO`, not shipped logic.
- **Judge model + cost:** the template defaults to a cheap judge model and documents the per-run cost ceiling as a kickstart-time knob.

### Remaining risks

- **claude-code path naming:** the `guides/evals/templates/{shared,agent_sdk,claude_api}/` layout reserves `guides/evals/templates/claude-code/` for the deferred follow-up, so no rename later — committing to that shape now.
- **Lint/type exclusion:** `guides/evals/templates/` contains app-importing Python that won't type-check pre-kickstart; pre-declare the exclusion in a kit-root `ruff.toml`/`mypy` config now (§1) and record it in root `CLAUDE.md` (§6), rather than leaving a note that a future validate-author might miss. Accepted trade-off: the self-contained shared modules that *could* be checked aren't, in exchange for one clean exclusion — the safety net is review-by-reading plus the kickstarted project's own `validate.sh`.
- **`prompt_sha` grouping is aspirational at two cases** (single prompt → one sha, nothing to group). `shared/README.md` should say *why* it exists (attribution across prompt revisions) so a contributor doesn't delete it as dead weight.

### 8. Done check (acceptance criteria -> plan, template-only flagged)

1. KICKSTART generates the scaffold for agent-sdk/claude-api only -> §6 (KICKSTART Phase 2 eval step, harness-gated). *Template-only / verified at kickstart.*
2. Minimal, worked-example-sized, tied to the two existing tools -> §2 (two cases on `list_agents` + `get_current_time`), §3 (minimal graders).
3. Golden dataset, checked-in/diffable/keyed by `prompt_sha`; >=1 assertion case + >=1 judge case -> §2 (YAML at `app/server/src/evals/cases/`; `result_contains` assertion case + `include_tool_results` judge case).
4. Hybrid grader: assertions on the run contract + LLM-judge with rubric -> §3 (`assertions.py` + overlay `extra_assertions.py` + `judge.py`, over `run_contract.RunRecord`).
5. `scripts/eval.sh` following script conventions -> §4 + §1 (`guides/evals/templates/eval.sh`). *Template-only / verified at kickstart.*
6. Mocked-vs-live split honored; not in `validate.sh`; `eval.sh` is itself the live gate -> §4, §6 (CLAUDE.md wording).
7. Contributor runs it, sees scored output, knows where to add cases -> §1 (`shared/README.md`), §3/§4 (`runner.py` prints + exits), §6 (`app/server/CLAUDE.md`). *Scored-output is template-only — demonstrated by the named, non-skippable "run `eval.sh` once" KICKSTART step (§6); no dry-run (locked, §7).*
8. KICKSTART.md + `app/server/CLAUDE.md` updated -> §6.
