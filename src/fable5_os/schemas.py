"""Structured output schemas for each agent.

Forcing each agent to return a typed, validated object does two things:

1. It removes free-form rambling, which is a common source of hallucination.
2. It makes every stage inspectable and testable.

Each schema carries an explicit ``confidence`` and an ``assumptions`` /
``open_questions`` field so the system can *surface* uncertainty instead of
hiding it behind confident-sounding prose.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    title: str = Field(description="Short imperative name of the step.")
    detail: str = Field(description="What is done and why, in one or two sentences.")
    done_when: str = Field(description="Concrete, checkable completion criterion.")


class PlannerOutput(BaseModel):
    """A concrete, verifiable plan."""

    goal: str = Field(description="Restatement of the user's goal in one sentence.")
    steps: List[PlanStep] = Field(description="Ordered steps to reach the goal.")
    risks: List[str] = Field(default_factory=list, description="Known risks or blockers.")
    assumptions: List[str] = Field(
        default_factory=list, description="Assumptions made because information was missing."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Self-assessed confidence in this plan (0-1)."
    )


class ResearchFinding(BaseModel):
    claim: str = Field(description="A single factual statement relevant to the goal.")
    support: str = Field(
        description="Why this is believed true. Say 'assumption' when there is no source."
    )
    verified: bool = Field(
        description="True only if backed by a concrete, checkable source; otherwise False."
    )


class ResearcherOutput(BaseModel):
    """Grounded context. Unverifiable items must be marked, never fabricated."""

    findings: List[ResearchFinding] = Field(default_factory=list)
    open_questions: List[str] = Field(
        default_factory=list, description="Things that must be checked with the user or a source."
    )
    confidence: float = Field(ge=0.0, le=1.0)


class DesignerOutput(BaseModel):
    """A simple, maintainable architecture or experience design."""

    summary: str = Field(description="One-paragraph description of the chosen design.")
    components: List[str] = Field(description="Named building blocks and their responsibility.")
    tradeoffs: List[str] = Field(default_factory=list, description="Explicit design tradeoffs.")
    assumptions: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class GeneratedFile(BaseModel):
    """A single source file the coder actually writes."""

    path: str = Field(
        description="Relative file path, e.g. 'password_checker.py'. No absolute paths or '..'."
    )
    content: str = Field(description="The complete, runnable file contents.")
    description: str = Field(description="One line on what this file does.")


class CoderOutput(BaseModel):
    """An implementation: real files plus a verification strategy."""

    approach: str = Field(description="How the solution is implemented, at a high level.")
    files: List[GeneratedFile] = Field(
        default_factory=list,
        description="Complete source files to write. Include at least the main runnable file.",
    )
    verification: List[str] = Field(
        description="How correctness is checked (tests, manual checks, invariants)."
    )
    assumptions: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ValidationIssue(BaseModel):
    stage: str = Field(description="Which stage the issue is about (plan/research/design/code).")
    problem: str = Field(description="What is wrong, missing, or unsupported.")
    severity: str = Field(description="One of: low, medium, high.")


class ValidatorOutput(BaseModel):
    """The self-check verdict over the whole run."""

    approved: bool = Field(description="True only when the result is coherent and grounded.")
    issues: List[ValidationIssue] = Field(default_factory=list)
    summary: str = Field(description="Plain-language verdict the user can read.")
    confidence: float = Field(ge=0.0, le=1.0)


# Map agent name -> schema, used by the agent runner.
AGENT_SCHEMAS = {
    "planner": PlannerOutput,
    "researcher": ResearcherOutput,
    "designer": DesignerOutput,
    "coder": CoderOutput,
    "validator": ValidatorOutput,
}
