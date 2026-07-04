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

        try:
            result = orchestrator.run(user_input)
        except Exception as exc:  # keep the REPL alive on any failure
            print(f"\n[error] {exc}")
            continue
        print("\n" + render_result(result))


if __name__ == "__main__":
    main()
