#!/usr/bin/env bash
#
# eval.sh — the live eval entry point (becomes scripts/eval.sh at kickstart).
#
# Invoking this script IS the gate: it requires the Anthropic API key, prints a
# cost warning, hits a REAL model, and spends tokens. Because of that credential
# + cost guard (the reason this script's shape differs from setup/start/validate),
# it is deliberately NOT run by scripts/validate.sh — the pre-PR gate stays
# mocked, fast, and free. It also does NOT require the caller to pre-set
# RUN_LIVE=1: a script whose whole purpose is the live run shouldn't make you
# opt in twice. For consistency with any shared recorded-tests helper that gates
# on that env var, eval.sh exports RUN_LIVE=1 itself (see step 2).
#
# See guides/evals/README.md for the rationale (hybrid grader, fresh-run-per-
# invocation, why this stays out of validate.sh).

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# === credential + cost guard ===
# This is the bullet the other three scripts don't carry: a real-model call costs
# tokens, so fail fast and loudly before we spend anything.
echo "=== guard: credential + cost check ==="
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set." >&2
  echo "eval.sh makes REAL model calls and cannot run without it." >&2
  echo "Export your key (e.g. 'export ANTHROPIC_API_KEY=sk-...') and re-run." >&2
  exit 1
fi
echo "WARNING: this runs the evals against a REAL model and spends tokens"
echo "(each golden case = one agent run, plus one judge call per judged case)."

# === run evals ===
# The runner produces a FRESH real-model run per golden case (non-deterministic;
# costs tokens) via the harness overlay's produce_run.py, then grades each run
# (deterministic assertions + any overlay extra_assertions + LLM judge) and prints
# the scored per-case + suite output itself.
echo "=== run evals (fresh real-model run per case, then grade) ==="
# Export RUN_LIVE for any shared recorded-tests helper that gates on it; the
# caller does NOT need to set it — invoking eval.sh already opted into the live run.
export RUN_LIVE=1
# TODO(kickstart): replace <import-root> with the project's configured src/-layout
# import root (resolved when the server package is named/packaged at kickstart),
# e.g. `uv run python -m app.evals.runner`.
uv run python -m <import-root>.evals.runner

# === scored output ===
# (No work here: the runner above prints the scored per-case + suite SuiteResult
# as its terminal step. This banner just marks where that output landed.)
echo "=== scored output printed above ==="

# === exit status ===
# Propagate the runner's exit code: with `set -e` a non-zero runner already
# aborted the script before this point, so reaching here means the suite passed.
echo "=== eval suite passed ==="
exit 0
