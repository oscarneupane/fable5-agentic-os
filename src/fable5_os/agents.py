"""Agent definitions, registry, and the runner that executes an agent turn.

``AgentSpec`` / ``AgentRegistry`` / ``build_default_agents`` describe *who* the
agents are. ``AgentRunner`` is *how* a turn is executed: it renders the prompt,
tries the live LLM with structured output, and falls back to the deterministic
offline generator on any failure. Either way it returns a validated schema
object, so downstream code never sees free-form text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from .config import Settings, load_settings
from .llm import build_chat_model, offline_generate, structured_schema_for
from .prompts import system_prompt_for


@dataclass
class AgentSpec:
    name: str
    role: str
    description: str
    instructions: List[str] = field(default_factory=list)


class AgentRegistry:
    def __init__(self) -> None:
        self.agents: Dict[str, AgentSpec] = {}

    def register(self, agent: AgentSpec) -> None:
        self.agents[agent.name] = agent

    def get(self, name: str) -> AgentSpec:
        return self.agents[name]

    def list_names(self) -> List[str]:
        return list(self.agents.keys())


def build_default_agents() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(
        AgentSpec(
            name="fable5",
            role="orchestrator",
            description="Main orchestrator that routes tasks and validates outputs.",
            instructions=[
                "Understand the user request fully before acting.",
                "Break complex work into smaller goals.",
                "Verify outputs before handing them off.",
                "Prefer concise, reliable steps over verbose speculation.",
            ],
        )
    )
    registry.register(
        AgentSpec(
            name="planner",
            role="planner",
            description="Creates execution steps and success criteria.",
            instructions=[
                "Create a concrete plan with milestones.",
                "Call out dependencies and risks.",
            ],
        )
    )
    registry.register(
        AgentSpec(
            name="researcher",
            role="researcher",
            description="Gathers facts and relevant context.",
            instructions=[
                "Use verified information and cite uncertainty clearly.",
                "Prefer evidence over assumptions.",
            ],
        )
    )
    registry.register(
        AgentSpec(
            name="designer",
            role="designer",
            description="Designs architecture and user experience.",
            instructions=[
                "Keep the design practical and user-friendly.",
                "Favor simple interfaces and maintainable structure.",
            ],
        )
    )
    registry.register(
        AgentSpec(
            name="coder",
            role="coder",
            description="Implements code and validates it.",
            instructions=[
                "Write minimal, readable code.",
                "Test changes and catch obvious issues before finishing.",
            ],
        )
    )
    registry.register(
        AgentSpec(
            name="validator",
            role="validator",
            description="Independent self-check over the whole run.",
            instructions=[
                "Verify coherence and grounding across all stages.",
                "Approve only when the result is consistent and supported.",
            ],
        )
    )
    return registry


def _render_context(context: Optional[Dict[str, Any]]) -> str:
    """Serialize upstream results so an agent can build on them."""

    if not context:
        return ""
    parts: List[str] = []
    for key, value in context.items():
        if value is None:  # e.g. research not ready yet when running in parallel
            continue
        if isinstance(value, BaseModel):
            value = value.model_dump()
        try:
            rendered = json.dumps(value, indent=2, default=str)
        except TypeError:
            rendered = str(value)
        parts.append(f"## {key}\n{rendered}")
    return "\n\n".join(parts)


class AgentRunner:
    """Executes a single agent turn and returns a validated schema object."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or load_settings()
        # One chat model per distinct model name, built lazily and cached so a
        # single provider/key can back different models for different agents.
        self._models: Dict[str, Any] = {}
        # Records the last live-call failure so a silent fallback is diagnosable.
        self.last_error: Optional[str] = None

    @property
    def mode(self) -> str:
        """'live' when live LLM calls are possible, otherwise 'offline'."""

        return "live" if self.settings.can_use_live_llm else "offline"

    def _model_for(self, agent_name: str):
        """Build (once) and return the chat model for an agent, or None offline.

        Cached by (provider, model) so agents sharing a config reuse one client.
        """

        provider = self.settings.provider_for(agent_name)
        model_name = self.settings.model_for(agent_name)
        cache_key = f"{provider}::{model_name}"
        if cache_key not in self._models:
            self._models[cache_key] = build_chat_model(
                self.settings, model=model_name, provider=provider
            )
        return self._models[cache_key]

    def run(
        self,
        agent_name: str,
        request: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> BaseModel:
        schema = structured_schema_for(agent_name)
        if schema is None:
            raise KeyError(f"Agent '{agent_name}' has no output schema")

        model = self._model_for(agent_name)
        if model is None:
            return offline_generate(agent_name, request)

        # Live path: force structured output so we get a validated object back.
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            system = system_prompt_for(agent_name, behavior=self.settings.behavior)
            context_block = _render_context(context)
            human = request if not context_block else (
                f"User request:\n{request}\n\nUpstream results to build on:\n{context_block}"
            )
            method = self.settings.structured_method
            if method:
                structured = model.with_structured_output(schema, method=method)
            else:
                structured = model.with_structured_output(schema)
            result = structured.invoke(
                [SystemMessage(content=system), HumanMessage(content=human)]
            )
            # ``with_structured_output`` returns an instance of ``schema``.
            if isinstance(result, schema):
                return result
            # Some providers return a dict; validate it into the schema.
            return schema.model_validate(result)
        except Exception as exc:
            # Any live failure (network, parsing, rate limit) degrades to offline
            # rather than crashing the run. Record it so the fallback is not silent.
            self.last_error = f"{agent_name}: {type(exc).__name__}: {exc}"
            return offline_generate(agent_name, request)
