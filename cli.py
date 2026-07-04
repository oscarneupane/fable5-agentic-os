"""Interactive CLI for Fable5 Agentic OS."""

import sys

from src.fable5_os.orchestrator import Fable5Orchestrator
from src.fable5_os.render import render_result

# Live model output can contain non-ASCII (emoji, curly quotes). Make stdout
# resilient on consoles that default to a legacy encoding (e.g. Windows cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


# A short, friendly line for each agent as it acts.
_AGENT_LINES = {
    "planner": "planner    breaking the request into a verifiable plan",
    "researcher": "researcher gathering grounded context",
    "designer": "designer   choosing the simplest architecture",
    "coder": "coder      writing runnable code",
    "validator": "validator  self-checking the whole run",
    "revise": "fable5     issues found -> requesting a revision",
}


def _progress(orchestrator):
    """Return an on_event callback that prints each agent as it finishes."""

    def on_event(node: str, delta: dict) -> None:
        line = _AGENT_LINES.get(node, node)
        model = ""
        if node in {"planner", "researcher", "designer", "coder", "validator"}:
            model = f"  [{orchestrator.settings.model_for(node)}]"
        print(f"  [ok] {line}{model}")

    return on_event


def main() -> None:
    orchestrator = Fable5Orchestrator()
    print("Fable5 Agentic OS")
    print(f"Mode: {orchestrator.mode.upper()}", end="")
    if orchestrator.mode == "offline":
        print("  (no API key / provider — running deterministic fallback)")
    else:
        print(f"  (provider: {orchestrator.settings.provider}, model: {orchestrator.settings.model})")
    flow = "parallel" if orchestrator.settings.parallel else "sequential"
    print(f"Flow: {flow}  |  behavior: {orchestrator.settings.behavior}")
    print("Type your request, or 'exit' to quit.")

    while True:
        try:
            user_input = input("\nYour request: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break

        print("\nAgents working...")
        try:
            result = orchestrator.run(user_input, on_event=_progress(orchestrator))
        except Exception as exc:  # keep the REPL alive on any failure
            print(f"\n[error] {exc}")
            continue
        print("\n" + render_result(result))


if __name__ == "__main__":
    main()
