"""LLM factory and the deterministic offline fallback.

This module is the single place that talks to LangChain. It exposes one live
path (a real chat model via ``init_chat_model``) and one offline path (a
deterministic, non-fabricating generator). The rest of the system does not care
which one is active — it just receives a validated schema object.

The offline path is what keeps the project honest and runnable with no API key:
instead of inventing content, it emits grounded, clearly-labeled output derived
only from the request.
"""

from __future__ import annotations

import os
from typing import Optional, Type

from pydantic import BaseModel

from .config import Settings
from .schemas import (
    CoderOutput,
    DesignerOutput,
    GeneratedFile,
    PlannerOutput,
    PlanStep,
    ResearcherOutput,
    ResearchFinding,
    ValidatorOutput,
)


def configure_langsmith(settings: Settings) -> None:
    """Enable LangSmith tracing via env vars when the user opted in.

    We set the canonical LangChain tracing variables so any LangChain/LangGraph
    call in this process is traced without further wiring.
    """

    if not settings.langsmith_tracing:
        return
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)


def build_chat_model(
    settings: Settings, model: Optional[str] = None, provider: Optional[str] = None
):
    """Return a LangChain chat model, or ``None`` if a live model is unavailable.

    ``model`` and ``provider`` override the defaults so a single run can mix
    providers/models per agent (e.g. GLM for the planner, OpenRouter for the
    coder). Returning ``None`` is a normal, expected outcome (no key, missing
    provider package, offline mode); callers fall back to the offline generator.
    """

    from .config import api_key_for, base_url_for, effective_provider_for, has_key_for

    provider = provider or settings.provider
    model = model or settings.model

    if settings.force_offline or not has_key_for(provider):
        return None

    try:
        from langchain.chat_models import init_chat_model

        kwargs = dict(
            model_provider=effective_provider_for(provider),
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            timeout=settings.request_timeout,
        )
        # The global base_url override only applies to the default provider.
        base_url = settings.base_url if provider == settings.provider and settings.base_url else base_url_for(provider)
        if base_url:
            kwargs["base_url"] = base_url
        key = api_key_for(provider)
        if key:
            kwargs["api_key"] = key

        return init_chat_model(model, **kwargs)
    except Exception:
        # Missing provider package, bad config, etc. Degrade to offline rather
        # than crash — reliability over features.
        return None


# --------------------------------------------------------------------------- #
# Offline deterministic generators
#
# These NEVER fabricate external facts. They restate the request, make the
# system's reasoning explicit, and clearly flag that no live model was used.
# --------------------------------------------------------------------------- #

_OFFLINE_NOTE = "Generated offline (no live LLM). Treat as a structured scaffold, not verified fact."


def _short(request: str, limit: int = 160) -> str:
    request = " ".join(request.split())
    return request if len(request) <= limit else request[: limit - 3] + "..."


def _offline_planner(request: str) -> PlannerOutput:
    goal = _short(request)
    return PlannerOutput(
        goal=f"Deliver: {goal}",
        steps=[
            PlanStep(
                title="Clarify scope",
                detail="Confirm the exact outcome and constraints for the request.",
                done_when="A one-sentence goal and explicit constraints are agreed.",
            ),
            PlanStep(
                title="Gather context",
                detail="Collect the facts and inputs needed before building anything.",
                done_when="Open questions are listed and known facts are recorded.",
            ),
            PlanStep(
                title="Design the approach",
                detail="Choose the simplest architecture or experience that fits.",
                done_when="Components and their responsibilities are named.",
            ),
            PlanStep(
                title="Implement and verify",
                detail="Build the minimal reliable solution with a verification step.",
                done_when="A concrete check confirms the result meets the goal.",
            ),
        ],
        risks=["Requirements may be underspecified; assumptions are flagged below."],
        assumptions=[_OFFLINE_NOTE],
        confidence=0.4,
    )


def _offline_researcher(request: str) -> ResearcherOutput:
    return ResearcherOutput(
        findings=[
            ResearchFinding(
                claim=f"The request concerns: {_short(request)}",
                support="Restated directly from the user's input.",
                verified=True,
            ),
            ResearchFinding(
                claim="No external sources were consulted in offline mode.",
                support="assumption",
                verified=False,
            ),
        ],
        open_questions=[
            "What concrete success criteria define 'done' for this request?",
            "Are there existing systems, constraints, or data this must integrate with?",
        ],
        confidence=0.35,
    )


def _offline_designer(request: str) -> DesignerOutput:
    return DesignerOutput(
        summary=(
            "A small, modular pipeline: each responsibility is a separate component with a "
            "single job, wired together by an orchestrator. Favors clarity and testability."
        ),
        components=[
            "Orchestrator: routes the request and enforces validation.",
            "Specialist stages: one component per responsibility (plan, research, design, build).",
            "Validator: independent self-check before results are finalized.",
        ],
        tradeoffs=[
            "More components means more wiring, but each stays simple and testable.",
        ],
        assumptions=[_OFFLINE_NOTE],
        confidence=0.4,
    )


def _offline_coder(request: str) -> CoderOutput:
    goal = _short(request, 100)
    # A minimal but genuinely runnable stub so the offline path still produces
    # a real file. It does not pretend to implement the request — it says so.
    main_py = (
        '"""Offline scaffold generated by Fable5.\n\n'
        f"Request: {goal}\n\n"
        "No live model was available, so this is a runnable starting point, not a\n"
        "full implementation. Replace the body of `run` with real logic.\n"
        '"""\n\n\n'
        "def run() -> None:\n"
        f'    print("Fable5 scaffold for: {goal}")\n'
        '    print("Replace run() with the real implementation.")\n\n\n'
        'if __name__ == "__main__":\n'
        "    run()\n"
    )
    test_py = (
        '"""Smoke test for the offline scaffold."""\n\n'
        "import main\n\n\n"
        "def test_run_does_not_crash() -> None:\n"
        "    main.run()\n"
    )
    return CoderOutput(
        approach=(
            "Offline: emit a minimal runnable scaffold (main.py + a smoke test) as a "
            "starting point. Replace the body with real logic once a model is available."
        ),
        files=[
            GeneratedFile(path="main.py", content=main_py, description="Runnable entry-point scaffold."),
            GeneratedFile(path="test_main.py", content=test_py, description="Smoke test for the scaffold."),
        ],
        verification=[
            "Run `python main.py` — it should print without error.",
            "Run the smoke test to confirm the entry point is importable.",
        ],
        assumptions=[_OFFLINE_NOTE],
        confidence=0.4,
    )


def _offline_validator(request: str) -> ValidatorOutput:
    return ValidatorOutput(
        approved=True,
        issues=[],
        summary=(
            "Offline run: the pipeline produced a coherent, clearly-labeled scaffold. No live "
            "model verified external facts, so treat findings as assumptions until checked."
        ),
        confidence=0.5,
    )


_OFFLINE_GENERATORS = {
    "planner": _offline_planner,
    "researcher": _offline_researcher,
    "designer": _offline_designer,
    "coder": _offline_coder,
    "validator": _offline_validator,
}


def offline_generate(agent_name: str, request: str) -> BaseModel:
    """Produce a deterministic, non-fabricating output for an agent."""

    generator = _OFFLINE_GENERATORS.get(agent_name)
    if generator is None:
        raise KeyError(f"No offline generator for agent '{agent_name}'")
    return generator(request)


def structured_schema_for(agent_name: str) -> Optional[Type[BaseModel]]:
    from .schemas import AGENT_SCHEMAS

    return AGENT_SCHEMAS.get(agent_name)
