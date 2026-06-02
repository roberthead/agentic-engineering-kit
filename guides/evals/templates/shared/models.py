"""Pydantic models for the YAML golden-case schema and the grader results.

Two families of model live here:

- The *case* schema (``GoldenCase`` and its parts) — what a ``cases/*.yaml`` file
  parses into. This is the contract a (possibly non-engineer) contributor writes
  against when adding a case.
- The *result* schema (``AssertionResult`` / ``JudgeResult`` / ``CaseResult`` /
  ``SuiteResult``) — what the graders produce and the runner aggregates and
  prints.

These models are self-contained: they import nothing from the app, so they are
import-clean pre-kickstart.
"""

from pydantic import BaseModel, Field


# --- Case schema (parsed from cases/*.yaml) ---------------------------------


class CaseInput(BaseModel):
    kind: str = "chat"
    content: str


class ToolCallAssertion(BaseModel):
    name: str
    # Top-level subset match against the matching tool call's ``input`` dict:
    # every key here must equal the same key in the call's input. Values are
    # compared by equality (a nested dict value must match exactly, not as a
    # sub-subset) — sufficient for the flat tool args in the worked example.
    args_contains: dict[str, object] = Field(default_factory=dict)
    # Substring match against the matching tool call's serialized ``output``.
    # Omit to skip the result check entirely.
    result_contains: str | None = None


class AssertionSpec(BaseModel):
    status: str = "ok"
    tool_calls: list[ToolCallAssertion] = Field(default_factory=list)
    # Only "non_empty_text" is shipped; `json_schema: <path>` is a documented
    # extension point (see shared/README.md).
    output_shape: str = "non_empty_text"


class RubricSpec(BaseModel):
    # Which tool outputs to splice into the judge prompt, by tool name.
    include_tool_results: list[str] = Field(default_factory=list)
    rubric: list[str]
    # Mean rubric score (1-5) must be >= threshold to pass.
    threshold: float = 4.0


class GoldenCase(BaseModel):
    id: str
    description: str
    # Ships null in YAML; injected at run time by the overlay's produce_run.py.
    prompt_sha: str | None = None
    input: CaseInput
    assertions: AssertionSpec
    # Present => run the LLM-judge path; absent => assertion-only case.
    judge: RubricSpec | None = None


# --- Result schema (produced by the graders, aggregated by the runner) ------


class AssertionResult(BaseModel):
    name: str
    passed: bool
    detail: str


class JudgeResult(BaseModel):
    score: float
    threshold: float
    passed: bool
    rationale: str


class CaseResult(BaseModel):
    case_id: str
    assertions: list[AssertionResult]
    judge: JudgeResult | None
    # All assertions green AND (judge is None OR judge.passed).
    passed: bool


class SuiteResult(BaseModel):
    results: list[CaseResult]
    passed: bool
