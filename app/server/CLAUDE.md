# Server

The backend server portion of the web app.

TODO: describe the role of the server — what it is responsible for (e.g., API surface, persistence, auth, background work, integrations) and what it is explicitly *not* responsible for.

## Evals

`app/server/src/evals/` is a live, maintained part of the workflow — not a one-off scaffold. The dataset is a set of checked-in golden cases (YAML, one file per case) under `src/evals/cases/*.yaml`. Each case declares an input, deterministic assertions over the persisted run, and an optional LLM-judge rubric.

- Run the suite with `scripts/eval.sh`. It produces a fresh run per case against a **real model** and grades it (deterministic assertions + judge). It spends tokens, so it's run on demand — never automatically.
- Evals are **not** part of `scripts/validate.sh`. The pre-PR gate stays mocked, fast, and deterministic; evals answer the separate question "is the agent good?"
- **Add a golden case when you add or expand a tool, or change behavior you care about.** A new tool with no case is an untested capability.

See `guides/evals/README.md` for the rationale (why hybrid grading, why evals live outside `validate.sh`, how the judge anchors on deterministic tool results).
