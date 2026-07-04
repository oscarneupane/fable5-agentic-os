"""The Fable5 LangGraph workflow.

The graph is a linear pipeline (plan -> research -> design -> code -> validate)
with a validation loop: if the validator finds blocking problems and revisions
remain, control returns to the planner with the issues in state. State is typed
and threaded end to end, and a checkpointer makes runs resumable.

Every node delegates the actual thinking to an :class:`AgentRunner`, so the
graph structure is independent of whether we run live or offline.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .agents import AgentRunner
from .schemas import (
    CoderOutput,
    DesignerOutput,
    PlannerOutput,
    ResearcherOutput,
    ValidatorOutput,
)
from .validation import decide_approval, run_deterministic_checks


class AgentState(TypedDict, total=False):
    request: str
    plan: Dict[str, Any]
    research: Dict[str, Any]
    design: Dict[str, Any]
    implementation: Dict[str, Any]
    validation: Dict[str, Any]
    issues: List[Dict[str, Any]]
    revision: int
    max_revisions: int
    mode: str
    # ``workflow`` is an append-only trace of which agent acted, in order.
    workflow: Annotated[List[str], operator.add]


def build_workflow(
    runner: Optional[AgentRunner] = None,
    max_revisions: Optional[int] = None,
    parallel: Optional[bool] = None,
):
    """Compile the workflow graph.

    Parameters
    ----------
    runner:
        The agent executor. Injected for testability; defaults to a fresh one.
    max_revisions:
        Overrides the configured revision budget for the validation loop.
    parallel:
        When true (default from settings), the researcher and designer run
        concurrently off the plan and fan back into the coder. When false, the
        classic linear pipeline is used.
    """

    runner = runner or AgentRunner()
    revision_budget = runner.settings.max_revisions if max_revisions is None else max_revisions
    parallel = runner.settings.parallel if parallel is None else parallel

    def planner_node(state: AgentState) -> AgentState:
        plan = runner.run("planner", state["request"])
        return {
            "plan": plan.model_dump(),
            "mode": runner.mode,
            "revision": state.get("revision", 0),
            "max_revisions": revision_budget,
            "workflow": ["planner: create execution plan"],
        }

    def researcher_node(state: AgentState) -> AgentState:
        research = runner.run(
            "researcher", state["request"], context={"plan": state.get("plan")}
        )
        return {
            "research": research.model_dump(),
            "workflow": ["researcher: collect grounded context"],
        }

    def designer_node(state: AgentState) -> AgentState:
        design = runner.run(
            "designer",
            state["request"],
            context={"plan": state.get("plan"), "research": state.get("research")},
        )
        return {
            "design": design.model_dump(),
            "workflow": ["designer: define architecture"],
        }

    def coder_node(state: AgentState) -> AgentState:
        code = runner.run(
            "coder",
            state["request"],
            context={
                "plan": state.get("plan"),
                "research": state.get("research"),
                "design": state.get("design"),
            },
        )
        return {
            "implementation": code.model_dump(),
            "workflow": ["coder: implementation approach + verification"],
        }

    def validator_node(state: AgentState) -> AgentState:
        # Rehydrate typed objects so deterministic checks can run.
        plan = PlannerOutput.model_validate(state["plan"])
        research = ResearcherOutput.model_validate(state["research"])
        design = DesignerOutput.model_validate(state["design"])
        code = CoderOutput.model_validate(state["implementation"])

        deterministic_issues = run_deterministic_checks(plan, research, design, code)

        verdict = runner.run(
            "validator",
            state["request"],
            context={
                "plan": state.get("plan"),
                "research": state.get("research"),
                "design": state.get("design"),
                "implementation": state.get("implementation"),
                "deterministic_issues": [i.model_dump() for i in deterministic_issues],
            },
        )
        assert isinstance(verdict, ValidatorOutput)

        # Merge model issues with our deterministic invariants, then apply the
        # configured strictness gate. Deterministic checks are authoritative:
        # a model cannot approve away a blocking structural problem, and (in
        # lenient/balanced mode) an otherwise-clean run is not vetoed by an
        # overly cautious model verdict.
        all_issues = deterministic_issues + list(verdict.issues)
        approved = decide_approval(verdict.approved, all_issues, runner.settings.strictness)

        merged = verdict.model_copy(update={"approved": approved, "issues": all_issues})
        return {
            "validation": merged.model_dump(),
            "issues": [i.model_dump() for i in all_issues],
            "revision": state.get("revision", 0),
            "workflow": ["validator: self-check and verdict"],
        }

    def route_after_validation(state: AgentState) -> str:
        validation = state.get("validation") or {}
        approved = validation.get("approved", False)
        revision = state.get("revision", 0)
        budget = state.get("max_revisions", revision_budget)
        if approved:
            return "done"
        if revision < budget:
            return "revise"
        return "done"

    def revise_node(state: AgentState) -> AgentState:
        """Bump the revision counter before looping back to the planner."""

        return {
            "revision": state.get("revision", 0) + 1,
            "workflow": ["fable5: request revision after validation"],
        }

    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("designer", designer_node)
    graph.add_node("coder", coder_node)
    graph.add_node("validator", validator_node)
    graph.add_node("revise", revise_node)

    graph.add_edge(START, "planner")
    if parallel:
        # Researcher and designer both depend only on the plan, so fan them out
        # to run concurrently, then fan back in: the coder waits for both.
        graph.add_edge("planner", "researcher")
        graph.add_edge("planner", "designer")
        graph.add_edge("researcher", "coder")
        graph.add_edge("designer", "coder")
    else:
        graph.add_edge("planner", "researcher")
        graph.add_edge("researcher", "designer")
        graph.add_edge("designer", "coder")
    graph.add_edge("coder", "validator")
    graph.add_conditional_edges(
        "validator",
        route_after_validation,
        {"revise": "revise", "done": END},
    )
    graph.add_edge("revise", "planner")

    return graph.compile(checkpointer=MemorySaver())
