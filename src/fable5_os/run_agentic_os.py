"""Convenience entry point for running the workflow once."""

from __future__ import annotations

import uuid
from typing import Any, Dict

from .agents import AgentRunner
from .workflow import build_workflow


def run_demo(
    request: str = "Create a reliable multi-agent operating system",
) -> Dict[str, Any]:
    """Run the full workflow once and return the final state."""

    runner = AgentRunner()
    app = build_workflow(runner)
    config = {"configurable": {"thread_id": f"demo-{uuid.uuid4().hex}"}}
    result = app.invoke({"request": request}, config=config)
    return result
