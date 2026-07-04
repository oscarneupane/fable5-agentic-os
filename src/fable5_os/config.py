"""Centralized configuration for Fable5 Agentic OS.

All environment-driven settings are read here so the rest of the codebase
never touches ``os.getenv`` directly. This keeps behavior predictable and
makes the system easy to configure and test.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict

from dotenv import load_dotenv

# Load a local .env file if present. This is a no-op when the file is absent.
load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Environment variable names that commonly hold a provider API key. We only use
# these to decide whether a live LLM call is even possible before attempting it.
_PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "google_vertexai": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistralai": "MISTRAL_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "cohere": "COHERE_API_KEY",
    "glm": "GLM_API_KEY",  # Zhipu AI, via OpenAI-compatible API
    "zhipuai": "ZHIPUAI_API_KEY",  # alias for GLM
    "openrouter": "OPENROUTER_API_KEY",  # gateway to many models (Claude, GPT, ...)
    "ollama": "",  # local; no key required
}

# Providers that speak the OpenAI wire protocol through a custom base URL.
# For these we route through model_provider="openai" and inject base_url + key.
_OPENAI_COMPATIBLE = {
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "zhipuai": "https://open.bigmodel.cn/api/paas/v4",
    "openrouter": "https://openrouter.ai/api/v1",
}


# --- Provider resolution, parameterized by provider name ---
# These are the single source of truth so a run can mix providers per agent.

def key_env_for(provider: str) -> str:
    return _PROVIDER_KEY_ENV.get(provider, "")


def effective_provider_for(provider: str) -> str:
    """The LangChain model_provider to initialize (OpenAI-compatible -> 'openai')."""
    return "openai" if provider in _OPENAI_COMPATIBLE else provider


def base_url_for(provider: str) -> str:
    return _OPENAI_COMPATIBLE.get(provider, "")


def api_key_for(provider: str) -> str:
    env_name = key_env_for(provider)
    return os.getenv(env_name, "") if env_name else ""


def has_key_for(provider: str) -> bool:
    """True when a key is present, or the provider needs none (e.g. ollama)."""
    env_name = key_env_for(provider)
    if env_name == "":
        return provider in _PROVIDER_KEY_ENV
    return bool(os.getenv(env_name))


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    provider: str = "openai"  # default provider...
    model: str = "gpt-4o-mini"  # ...and default model for every agent.
    # Per-agent overrides. Lets light agents use a cheap/free provider+model and
    # heavy agents a stronger one. e.g. agent_providers={"coder": "openrouter"}.
    agent_models: Dict[str, str] = field(default_factory=dict)
    agent_providers: Dict[str, str] = field(default_factory=dict)
    temperature: float = 0.1
    max_tokens: int = 1024
    request_timeout: int = 60
    base_url: str = ""  # override the API endpoint (used by OpenAI-compatible providers)
    # Method used to coerce structured output. "function_calling" is the most
    # widely compatible (GLM's strict json_schema support is incomplete).
    structured_method: str = "function_calling"

    # Reliability controls
    max_revisions: int = 1  # how many times the validator may request a revision
    force_offline: bool = False  # skip live calls entirely (deterministic mode)
    # Validator strictness: "lenient" | "balanced" | "strict".
    #   lenient  -> only high-severity issues block approval
    #   balanced -> high-severity issues block; the model's verdict is advisory (default)
    #   strict   -> medium+ issues block AND the model must also approve
    strictness: str = "balanced"

    # Agent behavior layer: "ponytail" (lazy-senior-dev, minimal code) or "none".
    behavior: str = "ponytail"

    # Run the researcher and designer concurrently (they both depend only on the
    # plan). Real wall-clock speedup; set false to run the classic linear pipeline.
    parallel: bool = True

    # Code generation
    write_code: bool = True  # write generated files to disk
    output_dir: str = "generated"  # base directory for written files

    # LangSmith tracing
    langsmith_tracing: bool = False
    langsmith_project: str = "fable5-agentic-os"

    def model_for(self, agent_name: str) -> str:
        """The model this agent should use (per-agent override, else the default)."""
        return self.agent_models.get(agent_name, self.model)

    def provider_for(self, agent_name: str) -> str:
        """The provider this agent should use (per-agent override, else default)."""
        return self.agent_providers.get(agent_name, self.provider)

    def base_url_for_agent(self, agent_name: str) -> str:
        """Endpoint for this agent. The global base_url override only applies to
        the default provider; per-agent providers use their own default URL."""
        provider = self.provider_for(agent_name)
        if provider == self.provider and self.base_url:
            return self.base_url
        return base_url_for(provider)

    def can_use_live_for(self, agent_name: str) -> bool:
        return not self.force_offline and has_key_for(self.provider_for(agent_name))

    # --- Default-provider convenience properties (used by single-model paths) ---
    @property
    def provider_key_env(self) -> str:
        return key_env_for(self.provider)

    @property
    def effective_provider(self) -> str:
        return effective_provider_for(self.provider)

    @property
    def effective_base_url(self) -> str:
        return self.base_url or base_url_for(self.provider)

    @property
    def api_key(self) -> str:
        return api_key_for(self.provider)

    @property
    def has_api_key(self) -> bool:
        return has_key_for(self.provider)

    @property
    def can_use_live_llm(self) -> bool:
        """True if the default provider OR any per-agent provider can go live."""
        if self.force_offline:
            return False
        providers = {self.provider, *self.agent_providers.values()}
        return any(has_key_for(p) for p in providers)


# Agents that can be individually pointed at a different model.
_AGENT_NAMES = ("planner", "researcher", "designer", "coder", "validator")


def _load_agent_overrides(prefix: str) -> Dict[str, str]:
    """Read FABLE5_<PREFIX>_<AGENT> overrides (e.g. FABLE5_MODEL_CODER)."""
    overrides: Dict[str, str] = {}
    for name in _AGENT_NAMES:
        value = os.getenv(f"FABLE5_{prefix}_{name.upper()}", "").strip()
        if value:
            overrides[name] = value
    return overrides


def load_settings() -> Settings:
    """Build a :class:`Settings` snapshot from the current environment."""

    tracing = _get_bool("LANGSMITH_TRACING") or _get_bool("LANGCHAIN_TRACING_V2")
    return Settings(
        provider=os.getenv("FABLE5_PROVIDER", "openai").strip(),
        model=os.getenv("FABLE5_MODEL", "gpt-4o-mini").strip(),
        agent_models=_load_agent_overrides("MODEL"),
        agent_providers=_load_agent_overrides("PROVIDER"),
        base_url=os.getenv("FABLE5_BASE_URL", "").strip(),
        structured_method=os.getenv("FABLE5_STRUCTURED_METHOD", "function_calling").strip(),
        temperature=_get_float("FABLE5_TEMPERATURE", 0.1),
        max_tokens=_get_int("FABLE5_MAX_TOKENS", 1024),
        request_timeout=_get_int("FABLE5_TIMEOUT", 60),
        max_revisions=_get_int("FABLE5_MAX_REVISIONS", 1),
        force_offline=_get_bool("FABLE5_OFFLINE", False),
        strictness=os.getenv("FABLE5_STRICTNESS", "balanced").strip().lower(),
        behavior=os.getenv("FABLE5_BEHAVIOR", "ponytail").strip().lower(),
        parallel=_get_bool("FABLE5_PARALLEL", True),
        write_code=_get_bool("FABLE5_WRITE_CODE", True),
        output_dir=os.getenv("FABLE5_OUTPUT_DIR", "generated").strip(),
        langsmith_tracing=tracing,
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "fable5-agentic-os").strip(),
    )
