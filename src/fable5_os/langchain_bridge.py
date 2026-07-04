"""Backwards-compatible LangChain integration layer.

The real integration now lives in :mod:`fable5_os.llm` (model factory + offline
fallback) and :mod:`fable5_os.config` (settings). This module is kept as a thin,
stable adapter so older imports keep working.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .config import Settings, load_settings
from .llm import build_chat_model, configure_langsmith


class LangChainBridge:
    """Adapter that reports how the orchestrator will reach an LLM."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.model_name = model_name or self.settings.model
        configure_langsmith(self.settings)

    def build_run(self, request: str) -> Dict[str, Any]:
        model = build_chat_model(self.settings)
        return {
            "model": self.model_name,
            "provider": self.settings.provider,
            "request": request,
            "mode": "live" if model is not None else "offline",
            "langsmith_tracing": self.settings.langsmith_tracing,
            "status": "ready",
        }
