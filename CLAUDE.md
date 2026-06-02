# Agentic Engineering Kit

A starter kit for new agentic engineering projects.

## Role

You are a development collaborator on the agentic engineering project that lives under `app/`. Read the project's `README.md` and any `CLAUDE.md` files within `app/` to understand what it is and how it's organized.

**First-contact check:** if `app/` does not yet contain implementation code (only this kit's documentation stubs and rulebooks — no `package.json`, `pyproject.toml`, source files, or `app/agents/concierge/`), the project hasn't been kickstarted yet. Read `KICKSTART.md` and follow its playbook before doing anything else. Once you see real implementation under `app/`, the kickstart playbook is no longer relevant — proceed as a normal development collaborator.

## Filename conventions

This repo uses two filename conventions deliberately. Know the difference:

- **`README.md`** — documentation. Audience is humans browsing the repo, plus you when you need context. *Reference material, not instructions.* The root `README.md` is the project's front door; the `README.md` files under `guides/` explain the **rationale** behind each stack/harness choice (the *why*, plus alternatives considered). Read them for context. Don't treat them as a checklist to execute.
- **`CLAUDE.md`** — instructions to you. Loaded into your context automatically (this root one eagerly, nested ones lazily when you touch files in their subtree). Written as live rules for how to work in that part of the codebase. *Follow them.*

If a `README.md` and a `CLAUDE.md` appear to disagree on what you should do, `CLAUDE.md` wins.

## Layout

Two top-level concerns: **how to set the project up** (`guides/`) and **what the project becomes** (`app/`).

### `guides/` — harness and stack guides

- `guides/harnesses/` — three mutually exclusive playbooks for the agent harness. Pick one:
  - `guides/harnesses/claude-code/` — interact directly via the Claude Code CLI. Agents are defined as `app/agents/<name>/prompt.md`; artifacts are published as a static site under `app/site/` (Astro).
  - `guides/harnesses/agent-sdk/` — Anthropic Claude Agent SDK as the harness, driven through an application UI. Agentic software written in python.
  - `guides/harnesses/claude-api/` — custom harness built on the Claude API, driven through an application UI. Agentic software written in python.
- `guides/client/` — recommended (default) frontend tech stack and a discussion of alternatives. **Applies to `agent-sdk` and `claude-api` harnesses only.**
- `guides/server/` — recommended (default) backend tech stack (Python: FastAPI, SQLAlchemy 2.x async, Postgres, `uv`). **Applies to `agent-sdk` and `claude-api` harnesses only.**
- `guides/evals/` — rationale guide for evaluating agent behavior: turning runs into a regression suite. **Applies to all three harnesses**, but with different substrate — DB-backed runs (`agent_runs` + `tool_calls` + `run_events`) for `agent-sdk` and `claude-api`; CLI sessions and Astro artifacts for `claude-code`.

### `app/` — your project

The shape of `app/` depends on which harness you picked:

**`claude-code` harness** — no server, no SPA client.

- `app/agents/<name>/prompt.md` — system prompt defining each agent's role, goals, and behavior.
- `app/site/` — Astro static site for agent-authored artifacts. Source under `src/content/`; build output `dist/` is gitignored and never hand-edited.

**`agent-sdk` and `claude-api` harnesses** — a web project with a server and a client.

- `app/server/CLAUDE.md` — live rules for working in the server: role, conventions, working instructions distilled from `guides/server/`.
- `app/client/CLAUDE.md` — live rules for working in the client: role, conventions, working instructions distilled from `guides/client/`.

### `scripts/` — developer entry points

The scripts here are the canonical entry points for working with the project — for humans and for you. They abstract over the harness choice so anyone can set up, run, and validate the project without knowing whether it's `uv` + `npm`, Astro, or something else underneath. **Create all three during kickstart** and tailor each to the harness you picked — all three have meaningful work for setup, start, and validate, so don't omit any. When the run/test/build story changes during normal development, keep them in sync — a stale `validate.sh` is worse than none.

- **`scripts/setup.sh`** — install dependencies and run idempotent seeds. Must be safe to re-run: `uv sync`, `npm install`, `alembic upgrade head`, and any seed data that's keyed/upserted. A new contributor should be one command from a working environment.
- **`scripts/start.sh`** — spin up all dev services and, when running interactively, open the app in the browser (skip the open if `$CI` is set or stdout isn't a TTY; use `open` on macOS, `xdg-open` elsewhere). For multi-service projects (`agent-sdk`, `claude-api`), start everything in parallel, **prefix each child's output with its service name** so interleaved logs stay readable (e.g. `npx concurrently --names server,client --prefix-colors blue,green ...`, or a `sed`-prefix per child), and ensure Ctrl-C cleans up children (`trap` + `wait`). For single-service projects (`claude-code`), this may just serve the static site.
- **`scripts/validate.sh`** — the pre-PR / pre-commit check. Run all linters, type checkers, test suites, and any production build. This is the correctness gate CI uses to decide whether a change can merge — not the full CI pipeline (deploy, secret scanning, etc. live in CI config, not here). If it's too slow for developers to run locally before pushing, it's the wrong check — split or speed it up rather than skip steps.

Conventions for every script in this directory:

- `#!/usr/bin/env bash` and `set -euo pipefail`. Fail fast.
- Resolve paths from the repo root so scripts work from any cwd. Standard idiom at the top of each script:

  ```bash
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  ```

- Exit non-zero on any failure. Don't swallow errors to keep going.
- Print a short banner before each step (`=== step name ===`) so failures are easy to locate in the output.
