"""Human-friendly rendering of a run result.

Kept separate from the CLI so the same formatting can be reused by ``main.py``,
tests, or a future UI. Pure functions, no I/O.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _bullets(items: List[Any], indent: str = "  ") -> str:
    if not items:
        return f"{indent}(none)"
    return "\n".join(f"{indent}- {item}" for item in items)


def render_result(result: Dict[str, Any]) -> str:
    """Turn an orchestrator result into a readable, sectioned report."""

    lines: List[str] = []
    mode = result.get("mode", "unknown")
    banner = "LIVE (LLM)" if mode == "live" else "OFFLINE (deterministic, no external facts verified)"
    lines.append("=" * 68)
    lines.append(f"Fable5 result  |  mode: {banner}")
    lines.append("=" * 68)
    lines.append(f"Request: {result.get('request', '')}")

    flow = "parallel (researcher + designer concurrent)" if result.get("parallel") else "sequential"
    elapsed = result.get("elapsed_seconds")
    timing = f"   |   {elapsed}s" if elapsed is not None else ""
    lines.append(f"Flow: {flow}{timing}")

    verdict = "APPROVED" if result.get("approved") else "NEEDS REVIEW"
    lines.append(f"Verdict: {verdict}   |   revisions: {result.get('revisions', 0)}")

    plan = result.get("plan") or {}
    lines.append("\n[Plan]")
    lines.append(f"  Goal: {plan.get('goal', '')}")
    for step in plan.get("steps", []):
        lines.append(f"  - {step.get('title')}: {step.get('detail')}")
        lines.append(f"      done when: {step.get('done_when')}")
    if plan.get("assumptions"):
        lines.append("  Assumptions:")
        lines.append(_bullets(plan["assumptions"], "    "))

    research = result.get("research") or {}
    lines.append("\n[Research]")
    for finding in research.get("findings", []):
        mark = "verified" if finding.get("verified") else "unverified"
        lines.append(f"  [{mark}] {finding.get('claim')}  ({finding.get('support')})")
    if research.get("open_questions"):
        lines.append("  Open questions:")
        lines.append(_bullets(research["open_questions"], "    "))

    design = result.get("design") or {}
    lines.append("\n[Design]")
    lines.append(f"  {design.get('summary', '')}")
    if design.get("components"):
        lines.append("  Components:")
        lines.append(_bullets(design["components"], "    "))

    code = result.get("implementation") or {}
    lines.append("\n[Implementation]")
    lines.append(f"  {code.get('approach', '')}")
    for f in code.get("files", []):
        lines.append(f"  file: {f.get('path')} - {f.get('description', '')}")
    if code.get("verification"):
        lines.append("  Verification:")
        lines.append(_bullets(code["verification"], "    "))

    written = result.get("written_files", [])
    if written:
        lines.append("\n[Files written]")
        for w in written:
            if w.get("written"):
                lines.append(f"  [ok]   {w.get('path')}")
            else:
                lines.append(f"  [FAIL] {w.get('path')} - {w.get('error')}")

    lines.append("\n[Validation]")
    validation = result.get("validation") or {}
    lines.append(f"  {validation.get('summary', '')}")
    issues = result.get("issues", [])
    if issues:
        lines.append("  Issues:")
        for issue in issues:
            lines.append(
                f"    - [{issue.get('severity')}] ({issue.get('stage')}) {issue.get('problem')}"
            )

    lines.append("\n[Trace]")
    lines.append(_bullets(result.get("workflow", []), "  "))
    return "\n".join(lines)
