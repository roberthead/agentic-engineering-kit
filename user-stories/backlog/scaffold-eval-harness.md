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

- Decisions already made with the user: hybrid grader; local/manual `scripts/eval.sh` (no CI wiring); `agent-sdk` + `claude-api` first.
- **Deferred follow-up:** a `claude-code` eval scaffold (CLI-against-prompts, score artifacts). Worth its own backlog story once this lands and the guide's claude-code section is validated against a real attempt.
- Watch the tension the user flagged: don't over-scaffold. The day-one app has only the concierge + two tools; the eval should be small enough to read in one sitting and obviously extensible, mirroring the kit's minimalism ("default to the smallest loop... grow it only when evals demand it").
- `scripts/eval.sh` becomes a fourth canonical script. The CLAUDE.md `scripts/` section currently enumerates exactly three (setup/start/validate) and says "Create all three during kickstart" — reconcile that wording if eval becomes a standard fourth entry point, or keep eval harness-conditional and say so.

## Implementation Plan

[to be filled in by /stories plan]
