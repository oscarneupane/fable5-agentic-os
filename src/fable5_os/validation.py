"""Deterministic self-checks run over agent outputs.

The validator agent (LLM) gives a judgment call, but we also run cheap,
deterministic invariants that do not depend on any model. These catch the most
common failure modes — empty stages, over-confidence without support, and
missing verification — regardless of whether we ran live or offline.
"""

from __future__ import annotations

from typing import List

from .schemas import (
    CoderOutput,
    DesignerOutput,
    PlannerOutput,
    ResearcherOutput,
    ValidationIssue,
)


def _issue(stage: str, problem: str, severity: str) -> ValidationIssue:
    return ValidationIssue(stage=stage, problem=problem, severity=severity)


def check_plan(plan: PlannerOutput) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not plan.steps:
        issues.append(_issue("plan", "Plan has no steps.", "high"))
    for i, step in enumerate(plan.steps):
        if not step.done_when.strip():
            issues.append(
                _issue("plan", f"Step {i + 1} ('{step.title}') has no completion criterion.", "medium")
            )
    if plan.confidence >= 0.8 and not plan.risks:
        issues.append(
            _issue("plan", "High confidence but no risks identified - likely overconfident.", "low")
        )
    return issues


def check_research(research: ResearcherOutput) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    # A finding marked verified must actually cite support, not "assumption".
    for finding in research.findings:
        if finding.verified and finding.support.strip().lower() in {"", "assumption", "n/a"}:
            issues.append(
                _issue(
                    "research",
                    f"Claim marked verified without real support: '{finding.claim[:60]}'",
                    "high",
                )
            )
    if not research.findings and not research.open_questions:
        issues.append(_issue("research", "Research produced neither findings nor open questions.", "medium"))
    return issues


def check_design(design: DesignerOutput) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not design.components:
        issues.append(_issue("design", "Design lists no components.", "high"))
    if not design.tradeoffs:
        issues.append(_issue("design", "No tradeoffs stated - every real design has some.", "low"))
    return issues


def check_code(code: CoderOutput) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not code.verification:
        issues.append(_issue("code", "No verification strategy provided.", "high"))
    if not code.approach.strip():
        issues.append(_issue("code", "Implementation approach is empty.", "high"))
    if not code.files:
        issues.append(_issue("code", "No code files were generated.", "medium"))
    for f in code.files:
        if not f.content.strip():
            issues.append(_issue("code", f"Generated file '{f.path}' is empty.", "medium"))
    return issues


def run_deterministic_checks(
    plan: PlannerOutput,
    research: ResearcherOutput,
    design: DesignerOutput,
    code: CoderOutput,
) -> List[ValidationIssue]:
    """Run all invariant checks and return the combined issue list."""

    issues: List[ValidationIssue] = []
    issues += check_plan(plan)
    issues += check_research(research)
    issues += check_design(design)
    issues += check_code(code)
    return issues


def has_blocking_issues(issues: List[ValidationIssue]) -> bool:
    """A run is blocked only by high-severity issues (default 'balanced' gate)."""

    return any(issue.severity == "high" for issue in issues)


# Severity ordering used by the strictness gate.
_SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}


def _block_threshold(strictness: str) -> int:
    """Minimum severity rank that blocks approval, per strictness level."""

    if strictness == "strict":
        return _SEVERITY_RANK["medium"]  # medium+ blocks
    # lenient and balanced both block only on high
    return _SEVERITY_RANK["high"]


def is_blocked(issues: List[ValidationIssue], strictness: str = "balanced") -> bool:
    """True when any issue meets the blocking threshold for this strictness."""

    threshold = _block_threshold(strictness)
    return any(_SEVERITY_RANK.get(i.severity, 2) >= threshold for i in issues)


def decide_approval(
    model_approved: bool, issues: List[ValidationIssue], strictness: str = "balanced"
) -> bool:
    """Final approval gate combining the model verdict with deterministic issues.

    - lenient / balanced: approve unless a blocking issue exists (model verdict
      is advisory — it cannot veto an otherwise-clean run).
    - strict: approve only when the model approves AND nothing blocks.
    """

    blocked = is_blocked(issues, strictness)
    if strictness == "strict":
        return model_approved and not blocked
    return not blocked
