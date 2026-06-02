# Eval templates

This directory holds the **worked-example half** of the evals work: inert, copyable template code (Python, bash, YAML) that the kickstart playbook copies into a real project. It is the companion to the rationale guide one level up — see [`../README.md`](../README.md) for the *why* (hybrid grader, dataset format, thresholds, the mocked-vs-live split).

## Reference code, not live code

Everything here is **reference code, not live code.** The template Python imports app modules (the concierge runner, the project's `Settings`, the persisted-run substrate) that do not exist until a project is kickstarted. So:

- These files do **not** run, import, type-check, or lint cleanly in this kit repo as-is — that is expected and correct.
- `guides/evals/templates/` is **excluded from any kit-level lint/type gate** (pre-declared in the kit-root `ruff.toml` / `mypy.ini`, and recorded in the root `CLAUDE.md`). Do not "fix" the app-importing imports here; they are resolved at kickstart, not in the kit.
- The `# TODO(kickstart)` markers flag the seams a kickstart resolves (the import root in `eval.sh`, the `produce_run.py` wiring to the concierge runner, the `judge.py` Anthropic client + model from `Settings`).

## Scope

The templates cover the two harnesses that share a persisted-run substrate: **`agent-sdk`** and **`claude-api`**. The `claude-code` harness has no DB and needs a fundamentally different scaffold (run the CLI against `prompt.md`, score Astro artifacts); it is **deferred** to its own follow-up story, with `guides/evals/templates/claude-code/` reserved for it.

## What gets copied where, at kickstart

| Template (here) | Copy target (in the kickstarted project) |
| --- | --- |
| `shared/` | `app/server/src/evals/` (the harness-agnostic core) |
| `agent_sdk/` **or** `claude_api/` overlay | merged **on top of** `app/server/src/evals/` |
| `eval.sh` | `scripts/eval.sh` |

The overlay is merged onto the already-copied `shared/` tree; there is no filename collision (the only overlay files are `produce_run.py`, plus `extra_assertions.py` for `claude-api`). The eval package lands under the server guide's `src/` layout at `app/server/src/evals/` — not a top-level `app/server/evals/` — so `eval.sh` invokes it through the project's configured import root.

## A note on directory names

The overlay directory names use **underscores** (`agent_sdk/`, `claude_api/`) because they become Python packages. They map to the **hyphenated** harness names used everywhere else (`agent-sdk`, `claude-api`). Kickstart translates between the two when it picks the overlay to copy.

## See also

- [`../README.md`](../README.md) — the rationale guide these templates instantiate.
- [`shared/README.md`](shared/README.md) — the contributor doc that travels into `app/server/src/evals/`: how to run the evals and how to add a golden case.
