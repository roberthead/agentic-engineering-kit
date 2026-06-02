# Story: Add Evals Guide

## Summary

AS a developer kickstarting a project from this kit

I WANT a guide that explains how to evaluate agents — and makes the dataset, grader, and where-it-runs decisions for me

SO THAT "evals are covered elsewhere" points at something real instead of a gap, and the kickstart scaffold has a rationale to instantiate.

## Context

The kit currently treats evals as an explicit non-goal. `guides/harnesses/claude-api/README.md` says so three times ("Skip... evals" line 11; "doesn't cover evals or RAG" line 28; "does not cover... evals" line 62), and no harness scaffolds an eval suite. But the substrate is already designed for it: the agent-sdk guide calls an `agent_runs` row + its `tool_calls` + `run_events` children "the unit of evaluation" and persists `prompt_sha` specifically so evals can group by it for regression attribution. The problem is purely that the "elsewhere" those guides defer to does not exist.

This guide is the *rationale* half of the evals work (the `guides/server/` pattern). The kickstart scaffold (see `scaffold-eval-harness`) is the *worked-example* half that instantiates these decisions. Guide first — it makes the calls the scaffold then implements.

## Acceptance Criteria

- A new `guides/evals/README.md` exists as a peer to `guides/server/` and `guides/client/`, following the same README-as-rationale convention (the *why* plus alternatives considered, not a checklist).
- The guide adopts a **hybrid grader strategy** as the default: deterministic assertions on persisted run state (status, tool calls made, output shape) for wiring/structure, plus **LLM-as-judge against a rubric** for open-ended answer quality. It explains when each applies and why the split mirrors the kit's existing mocked-vs-live test split.
- The guide specifies the **dataset properties** (golden cases as checked-in files that diff cleanly in review, keyed by `prompt_sha` so regressions are attributable, consistent with the agent-sdk guide's grouping convention) and intentionally **defers the exact file format and path** to the `scaffold-eval-harness` story rather than pre-committing them. _(Reworded at finish to match the locked decision; originally read "dataset format and location," which conflicted with the deferral.)_
- The guide takes a clear stance on **where evals run**: local/manual via a `scripts/eval.sh` entry point, run on demand. It explicitly defers CI/nightly automation to a later story and explains *why* real-model evals don't belong in `scripts/validate.sh` (non-determinism, cost, latency — echoing the existing "Avoid running every CI build against a real model" warning).
- The guide has **per-harness sections** covering the substrate divergence:
  - `agent-sdk` / `claude-api` — evals build on the persisted `agent_runs`/`tool_calls`/`run_events` rows.
  - `claude-code` — no DB; evals run the CLI against `prompt.md` files and score the Astro artifacts. (Guide covers the approach even though its scaffold is deferred.)
- The guide documents **regression thresholds / scoring** at least conceptually: how a judge score becomes pass/fail, how to set a threshold, how to read a drop as a prompt regression vs. a wiring regression.
- "Alternatives considered" covers at least: assertion-only, LLM-judge-primary, and any hosted/third-party eval tooling, with the trade-off that led to the hybrid default.
- Cross-references are updated so the three "evals covered elsewhere" disclaimers in `claude-api/README.md` (and the agent-sdk equivalent) now link to `guides/evals/README.md` instead of pointing nowhere.

## Notes

- Decisions already made with the user: hybrid grader (assertions + judge); local/manual `scripts/eval.sh` only (CI deferred); guide covers all three harnesses even though the scaffold story starts with two.
- Keep `CLAUDE.md`'s "Layout" section honest if this lands: `guides/evals/` becomes a new top-level guide concern alongside `server/`, `client/`, and the harness guides. The note that `server/`/`client/` apply to "agent-sdk and claude-api only" has an analog here — the evals guide applies to all three but with different substrate.
- This is reference material, not instructions — audience is humans plus the agent needing context. Don't write it as a procedure to execute.

## Implementation Plan

### Overview

Add a new `guides/evals/README.md` as a peer rationale guide to `guides/server/` and `guides/client/`, written in the same README-as-rationale voice (the *why* plus alternatives, not a checklist). Commit to a hybrid grader (deterministic assertions on persisted run state + LLM-as-judge against a rubric), checked-in golden cases keyed by `prompt_sha`, and local/manual `scripts/eval.sh` execution with CI deferred. Then fix the cross-references so the existing "evals covered elsewhere" disclaimers point at something real, and update the IA in root `CLAUDE.md` (and optionally root `README.md`).

### Section-by-section outline for `guides/evals/README.md`

Mirror the `guides/server/README.md` shape: one-line purpose, bold scope caveat, "At a glance" table, owns / does-not-own, per-decision rationale, alternatives near the end. Blank lines before and after every header.

1. **`# Evals Guide`** (title) + one-line purpose — "How to evaluate agents built with this kit, and the dataset/grader/where-it-runs decisions made for you."
2. **Scope caveat (bold lead paragraph, no header)** — analog of the server guide's caveat, but inverted: "This guide applies to **all three harnesses**, but the substrate differs — `agent-sdk`/`claude-api` evaluate persisted `agent_runs`; `claude-code` evaluates the CLI against `prompt.md` and the Astro artifacts." Names the scaffold story (`scaffold-eval-harness`) as the worked-example half, this as the rationale half.
3. **`## At a glance`** — decision table: Grader strategy → hybrid (assertions + LLM-judge); Dataset → checked-in golden cases keyed by `prompt_sha`; Where it runs → local/manual `scripts/eval.sh`; CI/nightly → deferred (later story); Scoring → judge score vs. threshold, pass/fail. One row per locked decision so a reader gets the stance in ten seconds.
4. **`## What evals own`** — answer-quality regression detection, wiring/structure verification on persisted run state, attributing a regression to a prompt change vs. a code change. The thing that makes "is this agent still good?" answerable.
5. **`## What evals do not own`** — not `scripts/validate.sh` (that's deterministic unit/integration tests against a mocked model); not CI gating (deferred); not observability/tracing (that's the OTel story in the harness guides — evals *consume* persisted run state, they don't produce traces); not prompt engineering itself.
6. **`## The unit of evaluation`** — forward-reference the agent-sdk guide's language: an `agent_runs` row + its `tool_calls` + `run_events` children. Explains *why* `prompt_sha` is persisted (group cases by it for regression attribution) and why that substrate is already eval-ready. Establishes the shared vocabulary the per-harness sections build on.
7. **`## The grader: a hybrid strategy`** — the core argument. Two graders: **deterministic assertions** on persisted run state (status `ok`, expected tool calls were made, output shape/JSON schema) for wiring/structure; **LLM-as-judge against a rubric** for open-ended answer quality. Explains when each applies and that this split *mirrors the kit's existing mocked-vs-live test split* (mocked tests catch wiring regressions; live/judge catch prompt regressions — agent-sdk lines 401-403).
8. **`## The dataset: golden cases`** — format and location. Checked-in files that diff cleanly in review (same rationale as `prompt.md` being files, agent-sdk line 202), each case keyed/labeled so a regression is attributable, grouped by `prompt_sha`. Propose a concrete location and format (e.g. `app/evals/cases/*.yaml` or `.jsonl`) as a *recommendation*, flagging that the scaffold story finalizes it.
9. **`## Scoring and regression thresholds`** — conceptual, not code. How a judge score (e.g. rubric 1-5 or pass-fraction) becomes pass/fail; how to set a threshold; how to read a drop: assertion failures = wiring regression, judge-score drop with assertions still green = prompt/quality regression. Ties back to `prompt_sha` grouping for attribution.
10. **`## Where evals run`** — local/manual via a `scripts/eval.sh` entry point, on demand. Explicitly defers CI/nightly to a later story and explains *why* real-model evals don't belong in `scripts/validate.sh`: non-determinism, cost, latency — echo the existing "Avoid running every CI build against a real model" warning (agent-sdk line 403). Contrast with `validate.sh` being the deterministic correctness gate.
11. **`## Per-harness substrate`** — three subsections:
    - **`### agent-sdk` / `### claude-api`** — build on persisted `agent_runs`/`tool_calls`/`run_events`; assertions query the DB rows; judge reads message content. `claude-api` adds per-call token/cost columns and `stop_reason` it can assert on.
    - **`### claude-code`** — no DB. Evals run the CLI against `prompt.md` files and score the Astro artifacts under `app/site/`. Golden cases are input prompts + expected artifact properties. Covered even though its scaffold is deferred.
12. **`## Alternatives considered`** — at least three, each with the trade-off that led to the hybrid default:
    - **Assertion-only** — cheap, deterministic, CI-friendly; can't measure answer quality.
    - **LLM-judge-primary** — measures quality; non-deterministic, costs money, judge itself needs validation (validate the judge against expert-labeled examples; track precision and recall separately — claude-api line 35).
    - **Hosted/third-party eval tooling** (e.g. Braintrust, LangSmith, Promptfoo) — fast to adopt; adds a dependency and pulls eval data out of the repo, breaking the checked-in/diffable-in-review property.
13. **`## References`** — link back to `guides/server/README.md`, `guides/harnesses/agent-sdk/README.md` (unit-of-evaluation section), and the `scaffold-eval-harness` story.

### Concrete edits to existing files

Verify line numbers at implementation time — they drift.

1. **`guides/harnesses/claude-api/README.md`** — three disclaimers, make each point at the new guide:
   - Line 11 ("...covered elsewhere") → change "covered elsewhere" to "covered in `guides/evals/README.md`".
   - Line 28 ("doesn't cover evals or RAG") → append "(evals: see `guides/evals/README.md`)".
   - Line 62 ("Add: prompt engineering, evals, RAG...") → make "evals" link to `guides/evals/README.md`.
2. **`guides/harnesses/agent-sdk/README.md`** — two changes:
   - Near the "unit of evaluation" text (line ~409, end of `## Observability`) add a one-line pointer: "How to turn that unit into a regression suite is in `guides/evals/README.md`." Highest-value placement — the language the new guide builds on lives here.
   - In `## What this guide does not cover` (starts ~line 411) add a bullet: "**Evals** (turning persisted runs into a regression suite) — `guides/evals/README.md`." The section currently lists server/client/auth/individual-agents but does not name evals; adding it keeps the disclaimer set symmetric with claude-api.
3. **Root `CLAUDE.md`** — in "Layout" → `guides/` enumeration, add `guides/evals/` as a sibling sub-concern with the caveat: "applies to all three harnesses, but with different substrate (DB-backed runs for agent-sdk/claude-api; CLI + Astro artifacts for claude-code)" — the explicit analog to the server/client "agent-sdk and claude-api only" caveat.
4. **Root `README.md`** — **no change** (decision locked: skip the pointer). The stack bullets are harness-stack-scoped and evals doesn't fit there.

### Decisions locked (resolved with user)

- **agent-sdk cross-ref:** do **both** — a one-line pointer near the unit-of-evaluation text (~409) *and* a bullet in "What this guide does not cover" (~411). They serve different readers.
- **Root README pointer:** **skip.** Leave the stack list alone.
- **Dataset format/location:** state the *properties* firmly (checked-in, diffable in review, keyed by `prompt_sha`) but leave exact format (`.yaml` vs `.jsonl`) and path (`app/evals/cases/`) to the `scaffold-eval-harness` story. The guide must not pre-commit a format.

### Remaining risks

- **`scripts/eval.sh` contract:** root `CLAUDE.md` documents `setup.sh`/`start.sh`/`validate.sh` as canonical and doesn't mention `eval.sh`. The guide introduces it as rationale only; actually creating `eval.sh` and registering it belongs to the scaffold story — keep this guide from implying the script already exists.
- **claude-code eval depth:** scaffold deferred, no DB, so this subsection is least concrete. Keep it to the substrate stance (inputs = prompts, scored = artifacts) and defer mechanics.
- **Forward-reference honesty:** `app/server/` does not exist yet (pre-kickstart). All DB-substrate references must read as forward-references to what the agent-sdk/server guides describe, not as live code.
- **`scripts/eval.sh` contract:** root `CLAUDE.md` documents `setup.sh`/`start.sh`/`validate.sh` as canonical and doesn't mention `eval.sh`. The guide introduces it as rationale; actually creating `eval.sh` and registering it belongs to the scaffold story — keep this guide from implying the script already exists.
- **claude-code eval depth:** scaffold deferred, no DB, so this subsection is least concrete. Keep it to the substrate stance (inputs = prompts, scored = artifacts) and defer mechanics.
- **Forward-reference honesty:** `app/server/` does not exist yet (pre-kickstart). All DB-substrate references must read as forward-references to what the agent-sdk/server guides describe, not as live code.

### Done check

| Acceptance criterion | Satisfied by |
|---|---|
| New `guides/evals/README.md` peer, README-as-rationale voice | Outline §1-13; voice mirrors `guides/server/README.md` |
| Hybrid grader default; mirrors mocked-vs-live test split | Outline §7 (+ §3 table) |
| Dataset format/location, keyed, `prompt_sha`-consistent | Outline §8 (+ §6) |
| Where evals run: local `scripts/eval.sh`, CI deferred, why not in `validate.sh` | Outline §10 |
| Per-harness substrate (DB vs. CLI/Astro), claude-code covered | Outline §11 |
| Regression thresholds / scoring conceptually | Outline §9 |
| Alternatives: assertion-only, judge-primary, hosted tooling | Outline §12 |
| Cross-refs in claude-api / agent-sdk point to the guide | Edits §1, §2 |
| Root `CLAUDE.md` Layout honest; all-three-but-different-substrate caveat | Edit §3 |
| Root `README.md` pointer | N/A — skipped (decision locked) |

## Learnings

### What went well

- **Locking decisions before implementing paid off.** By the time the writing agents ran, every contentious call (hybrid grader, defer format, skip README) was settled — so the parallel agents had zero ambiguity and produced near-final work in one pass.
- **File-disjoint parallelism** (guide vs. cross-reference edits) ran with no conflicts; both workstreams landed clean.
- **Grounding the guide in real quotes** from the existing guides gave it credibility — the review verified every quote was accurate and undistorted.

### What was surprising

- **The story-planner couldn't spawn its own sub-agents** in this environment and synthesized the specialist views itself. The plan was still solid, but the "team" was nominal at plan time — the real multi-agent value showed up at *implement* and *review*, not *plan*.
- **Writing a docs guide exposed a latent inconsistency in the kit itself:** root `CLAUDE.md` says "create all three scripts," but evals introduces a fourth (`scripts/eval.sh`). The rationale layer surfaced a seam in the existing instructions.
- **The single factual slip was inside the accuracy caveat** — the line meant to ensure forward-reference honesty ("`app/server/` does not exist yet") was itself wrong, since the stub directory exists. Forward-reference framing is easy to overshoot.

### What to do differently

- **Reconcile acceptance-criteria wording with locked decisions at decision time, not at finish** (the AC3 "format and location" vs. "defer format" conflict).
- **When forward-referencing not-yet-existing paths, check each against the actual tree** — stub dirs like `app/server/` exist even pre-kickstart.
- **Assign cross-story seams to an owning story explicitly** (the `eval.sh` fourth-script question) so they're not discovered in review.
