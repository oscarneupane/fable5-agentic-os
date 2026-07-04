"""Scripted, repeatable demo — ideal for recording.

Runs one request through the full pipeline with live agent streaming, prints the
report, then proves every generated Python file actually compiles.

    python demo.py                       # default request
    python demo.py "Build a JSON pretty-printer CLI"
    python demo.py --fast "..."          # no pacing pauses
"""

import sys
import time
import py_compile

from src.fable5_os.orchestrator import Fable5Orchestrator
from src.fable5_os.render import render_result

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

DEFAULT_REQUEST = "Build a CLI password-strength checker in Python"

_AGENT_LINES = {
    "planner": "planner    breaking the request into a verifiable plan",
    "researcher": "researcher gathering grounded context",
    "designer": "designer   choosing the simplest architecture",
    "coder": "coder      writing runnable code",
    "validator": "validator  self-checking the whole run",
    "revise": "fable5     issues found -> requesting a revision",
}


def _rule(char="-"):
    print(char * 68)


def main() -> None:
    args = sys.argv[1:]
    fast = "--fast" in args
    args = [a for a in args if a != "--fast"]
    request = " ".join(args).strip() or DEFAULT_REQUEST
    pause = (lambda s=0.0: None) if fast else time.sleep

    orchestrator = Fable5Orchestrator()
    s = orchestrator.settings

    _rule("=")
    print("  FABLE5 AGENTIC OS  —  live demo")
    _rule("=")
    print(f"  mode:     {orchestrator.mode.upper()}")
    print(f"  provider: {s.provider}   flow: {'parallel' if s.parallel else 'sequential'}   behavior: {s.behavior}")
    print()
    print(f"  > {request}")
    print()
    pause(0.8)
    print("Agents working...")

    def on_event(node, delta):
        line = _AGENT_LINES.get(node, node)
        model = f"  [{s.model_for(node)}]" if node in _AGENT_LINES and node != "revise" else ""
        print(f"  [ok] {line}{model}")

    result = orchestrator.run(request, on_event=on_event)
    pause(0.6)
    print()
    print(render_result(result))

    # Prove the generated code is real: compile every written .py file.
    written = [w for w in result.get("written_files", []) if w.get("written") and w["path"].endswith(".py")]
    if written:
        pause(0.6)
        print("\n[Compile check]")
        for w in written:
            path = w["path"]
            # written_files paths are relative to the run's output dir
            full = _find_written(path)
            try:
                py_compile.compile(full, doraise=True)
                print(f"  [ok]   {path} compiles")
            except Exception as exc:
                print(f"  [FAIL] {path}: {exc}")
        print("\nRun it yourself:")
        print(f"  python generated/run-*/<file>.py")


def _find_written(rel_path: str) -> str:
    """Locate a just-written file under the newest generated/run-* folder."""
    import glob
    import os

    runs = sorted(glob.glob("generated/run-*"), key=os.path.getmtime, reverse=True)
    for run in runs:
        candidate = os.path.join(run, rel_path)
        if os.path.exists(candidate):
            return candidate
    return rel_path


if __name__ == "__main__":
    main()
