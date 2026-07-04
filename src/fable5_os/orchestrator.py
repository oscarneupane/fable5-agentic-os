"""Fable5 orchestrator — the single entry point for running the system.

It owns configuration, wires up the agent runner and the LangGraph workflow,
executes a request end to end, and returns one structured, inspectable result.
It also reports which mode it ran in (live vs offline) so the user always knows
whether external facts were actually verified.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agents import AgentRegistry, AgentRunner, build_default_agents
from .config import Settings, load_settings
from .llm import configure_langsmith
from .schemas import GeneratedFile
from .workflow import build_workflow
from .writer import write_files


class Fable5Orchestrator:
    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        settings: Optional[Settings] = None,
        runner: Optional[AgentRunner] = None,
    ) -> None:
        self.settings = settings or load_settings()
        configure_langsmith(self.settings)
        self.registry = registry or build_default_agents()
        self.runner = runner or AgentRunner(self.settings)
        self._app = build_workflow(self.runner)

    @property
    def mode(self) -> str:
        return self.runner.mode

    def run(self, request: str, on_event=None) -> Dict[str, Any]:
        """Execute the full workflow for a request and return a structured result.

        Pass ``on_event(node_name, delta)`` to receive live progress as each
        agent finishes (used by the CLI to stream the pipeline in real time).
        """

        if not request or not request.strip():
            raise ValueError("Request cannot be empty")

        # A unique thread id keeps each run isolated in the checkpointer.
        run_id = uuid.uuid4().hex
        config = {"configurable": {"thread_id": f"run-{run_id}"}}
        started = time.time()
        if on_event is None:
            final_state = self._app.invoke({"request": request}, config=config)
        else:
            # Stream node-by-node updates so callers can show live progress.
            for chunk in self._app.stream(
                {"request": request}, config=config, stream_mode="updates"
            ):
                for node, delta in chunk.items():
                    on_event(node, delta or {})
            final_state = self._app.get_state(config).values
        elapsed = round(time.time() - started, 2)

        validation = final_state.get("validation") or {}
        written = self._write_generated_files(final_state.get("implementation"), run_id)

        return {
            "message": "Fable5 orchestrator completed the request.",
            "request": request,
            "mode": final_state.get("mode", self.mode),
            "parallel": self.settings.parallel,
            "elapsed_seconds": elapsed,
            "agents": self.registry.list_names(),
            "plan": final_state.get("plan"),
            "research": final_state.get("research"),
            "design": final_state.get("design"),
            "implementation": final_state.get("implementation"),
            "validation": validation,
            "issues": final_state.get("issues", []),
            "approved": bool(validation.get("approved", False)),
            "revisions": final_state.get("revision", 0),
            "written_files": written,
            "workflow": final_state.get("workflow", []),
            "langsmith_enabled": self.settings.langsmith_tracing,
        }

    def _write_generated_files(
        self, implementation: Optional[Dict[str, Any]], run_id: str
    ) -> List[Dict[str, Any]]:
        """Write the coder's files under output_dir/<run_id>/ (if enabled)."""

        if not self.settings.write_code or not implementation:
            return []
        raw_files = implementation.get("files") or []
        files = [GeneratedFile.model_validate(f) for f in raw_files]
        if not files:
            return []
        base_dir = str(Path(self.settings.output_dir) / f"run-{run_id[:8]}")
        return write_files(files, base_dir)

    def plan_workflow(self, request: str) -> List[str]:
        """Return the static high-level pipeline outline (no execution)."""

        return [
            "fable5: interpret the request",
            "planner: create a structured plan",
            "researcher: collect grounded context",
            "designer: define the architecture or experience",
            "coder: implement and verify the solution",
            "validator: self-check before finalizing",
        ]
