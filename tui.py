"""Live multi-agent dashboard — watch the subagents work in real time.

Each agent gets its own panel that lights up and spins while it works. The
researcher and designer sit side by side so you can see them run in parallel.

    python tui.py                          # default request
    python tui.py "Build a URL shortener in Python"

Requires: rich  (pip install rich  — already in requirements.txt)
"""

import sys
import threading
import time

# Emoji/box-drawing need UTF-8; on Windows the console often defaults to cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from src.fable5_os.orchestrator import Fable5Orchestrator
from src.fable5_os.agents import AgentRunner
from src.fable5_os.render import render_result

DEFAULT_REQUEST = "Build a CLI password-strength checker in Python"

ICONS = {
    "planner": "🧭",
    "researcher": "🔎",
    "designer": "📐",
    "coder": "⌨️",
    "validator": "✅",
}
AGENT_DESC = {
    "planner": "planning the steps",
    "researcher": "gathering context",
    "designer": "choosing architecture",
    "coder": "writing code",
    "validator": "self-checking",
}


class Dashboard:
    """Holds per-agent status and renders the live layout."""

    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.Lock()
        self.state = {
            name: {"status": "queued", "start": None, "end": None, "fallback": False,
                   "spinner": Spinner("dots")}
            for name in ICONS
        }
        self.request = ""
        self.started = time.time()

    # --- event hooks (called by AgentRunner, possibly from parallel threads) ---
    def start(self, name):
        with self.lock:
            st = self.state.get(name)
            if st:
                st["status"] = "running"
                st["start"] = time.time()

    def end(self, name, used_fallback):
        with self.lock:
            st = self.state.get(name)
            if st:
                st["status"] = "fallback" if used_fallback else "done"
                st["end"] = time.time()
                st["fallback"] = used_fallback

    # --- rendering ---
    def _panel(self, name):
        st = self.state[name]
        model = self.settings.model_for(name)
        icon = ICONS[name]
        status = st["status"]

        if status == "queued":
            body = Text("• queued", style="grey42")
            border = "grey37"
        elif status == "running":
            elapsed = time.time() - (st["start"] or time.time())
            body = st["spinner"]
            body.update(text=Text(f" {AGENT_DESC[name]}…  {elapsed:4.1f}s", style="cyan"))
            border = "cyan"
        elif status == "done":
            dur = (st["end"] or 0) - (st["start"] or 0)
            body = Text(f"✓ done   {dur:4.1f}s", style="bold green")
            border = "green"
        else:  # fallback
            dur = (st["end"] or 0) - (st["start"] or 0)
            body = Text(f"⚠ offline fallback   {dur:4.1f}s", style="yellow")
            border = "yellow"

        title = Text(f"{icon} {name}", style="bold")
        content = Group(body, Text(model, style="grey42"))
        return Panel(content, title=title, border_style=border, padding=(0, 1))

    def render(self):
        with self.lock:
            header = Panel(
                Group(
                    Text(f"> {self.request}", style="bold white"),
                    Text(
                        f"provider: {self.settings.provider}   "
                        f"flow: {'parallel' if self.settings.parallel else 'sequential'}   "
                        f"behavior: {self.settings.behavior}   "
                        f"elapsed: {time.time() - self.started:4.1f}s",
                        style="grey50",
                    ),
                ),
                title="FABLE5 AGENTIC OS  —  agents working",
                border_style="magenta",
            )
            arrow = Text("        ↓", style="grey37")
            par_label = Text("        ↓  (parallel)", style="grey37")
            parallel = Columns(
                [self._panel("researcher"), self._panel("designer")],
                equal=True, expand=True,
            )
            return Group(
                header,
                self._panel("planner"),
                par_label,
                parallel,
                arrow,
                self._panel("coder"),
                arrow,
                self._panel("validator"),
            )


def main():
    # legacy_windows=False forces the modern ANSI/UTF-8 path (Windows Terminal,
    # VS Code terminal) instead of the cp1252 win32 console renderer.
    console = Console(legacy_windows=False)
    request = " ".join(sys.argv[1:]).strip() or DEFAULT_REQUEST

    runner = AgentRunner()
    dash = Dashboard(runner.settings)
    dash.request = request
    runner.on_agent_start = dash.start
    runner.on_agent_end = dash.end

    orchestrator = Fable5Orchestrator(settings=runner.settings, runner=runner)

    holder = {}

    def work():
        try:
            holder["result"] = orchestrator.run(request)
        except Exception as exc:  # surface, don't hang the display
            holder["error"] = exc

    t = threading.Thread(target=work, daemon=True)
    with Live(dash.render(), console=console, refresh_per_second=12, transient=False) as live:
        t.start()
        while t.is_alive():
            live.update(dash.render())
            time.sleep(0.08)
        live.update(dash.render())  # final frame
    t.join()

    if "error" in holder:
        console.print(f"[red]Error:[/red] {holder['error']}")
        return
    console.print()
    console.print(render_result(holder["result"]))


if __name__ == "__main__":
    main()
