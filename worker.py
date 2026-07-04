"""A single agent, running in its own terminal window.

Launched by swarm.py — one of these per agent. It waits for the agents it
depends on to finish (by watching a shared run directory), runs its own agent,
shows a live status, and writes its result so downstream agents can pick it up.

    python worker.py <agent> <run_dir>
"""

import json
import os
import sys
import threading
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from src.fable5_os.agents import AgentRunner

# Each agent depends on these upstream result files (base names -> <name>.json).
AGENT_DEPS = {
    "planner": [],
    "researcher": ["plan"],
    "designer": ["plan"],
    "coder": ["plan", "research", "design"],
    "validator": ["plan", "research", "design", "implementation"],
}
# The result file this agent produces.
AGENT_OUT = {
    "planner": "plan",
    "researcher": "research",
    "designer": "design",
    "coder": "implementation",
    "validator": "validation",
}
ICON = {"planner": "🧭", "researcher": "🔎", "designer": "📐", "coder": "⌨️", "validator": "✅"}
DESC = {
    "planner": "breaking the request into a plan",
    "researcher": "gathering grounded context",
    "designer": "choosing the simplest architecture",
    "coder": "writing runnable code",
    "validator": "self-checking the whole run",
}


def _summary(agent, data):
    """A short, human line describing this agent's result."""
    if agent == "planner":
        return f"{len(data.get('steps', []))} steps · confidence {data.get('confidence', '?')}"
    if agent == "researcher":
        return f"{len(data.get('findings', []))} findings · {len(data.get('open_questions', []))} open questions"
    if agent == "designer":
        return f"{len(data.get('components', []))} components"
    if agent == "coder":
        return f"{len(data.get('files', []))} file(s) written"
    if agent == "validator":
        return ("APPROVED" if data.get("approved") else "needs review") + f" · {len(data.get('issues', []))} issues"
    return ""


def main():
    if len(sys.argv) < 3:
        print("usage: python worker.py <agent> <run_dir>")
        return
    agent = sys.argv[1]
    run_dir = sys.argv[2]
    request = open(os.path.join(run_dir, "request.txt"), encoding="utf-8").read().strip()
    runner = AgentRunner()
    model = runner.settings.model_for(agent)

    console = Console(legacy_windows=False)
    spinner = Spinner("dots")
    state = {"phase": "waiting", "detail": "", "result_line": ""}

    def render():
        icon = ICON.get(agent, "•")
        if state["phase"] == "waiting":
            spinner.update(text=Text(f" waiting for: {state['detail']}", style="yellow"))
            body, border = spinner, "yellow"
        elif state["phase"] == "working":
            spinner.update(text=Text(f" {DESC.get(agent, 'working')}…", style="cyan"))
            body, border = spinner, "cyan"
        else:  # done
            body = Text(f"✓ {state['result_line']}", style="bold green")
            border = "green"
        return Panel(
            Group(body, Text(model, style="grey42")),
            title=Text(f"{icon} {agent}", style="bold"),
            subtitle=Text(request[:52], style="grey50"),
            border_style=border,
            padding=(1, 2),
        )

    deps = AGENT_DEPS.get(agent, [])
    context = {}
    with Live(render(), console=console, refresh_per_second=12) as live:
        # 1) wait for upstream results
        for dep in deps:
            path = os.path.join(run_dir, f"{dep}.json")
            while not os.path.exists(path):
                state["phase"] = "waiting"
                state["detail"] = dep
                live.update(render())
                time.sleep(0.2)
            # brief settle so a half-written file is fully flushed
            time.sleep(0.15)
            context[dep] = json.load(open(path, encoding="utf-8"))

        # 2) run this agent (in a thread so the spinner keeps moving)
        state["phase"] = "working"
        live.update(render())
        holder = {}

        def work():
            holder["result"] = runner.run(agent, request, context or None)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        while t.is_alive():
            live.update(render())
            time.sleep(0.08)

        # 3) write result for downstream agents
        data = holder["result"].model_dump()
        out_path = os.path.join(run_dir, f"{AGENT_OUT[agent]}.json")
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, out_path)  # atomic: downstream never sees a half file

        state["phase"] = "done"
        state["result_line"] = _summary(agent, data)
        live.update(render())

    console.print(Text(f"\n{agent} done — this window can be closed.", style="grey50"))


if __name__ == "__main__":
    main()
