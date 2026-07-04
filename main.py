"""Non-interactive entry point: run one request and print the report."""

import sys

from src.fable5_os.orchestrator import Fable5Orchestrator
from src.fable5_os.render import render_result

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def main() -> None:
    orchestrator = Fable5Orchestrator()
    request = (
        "Build a multi-agent operating system for planning, research, design, and coding."
    )
    result = orchestrator.run(request)
    print(render_result(result))


if __name__ == "__main__":
    main()
