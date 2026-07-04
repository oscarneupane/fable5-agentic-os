"""Fable5 swarm — one terminal window per agent.

Opens a separate terminal window for each subagent. They coordinate through a
shared run directory: the planner runs first, then the researcher and designer
windows spring to life together (parallel), then the coder, then the validator.
This window stays as the orchestrator overview.

    python swarm.py "Build a URL shortener in Python"
    python swarm.py --panes "..."      # one window, split into panes (Windows Terminal)
    python swarm.py --headless "..."   # no windows (used for testing/CI)
"""

import json
import os
import shutil
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from src.fable5_os.config import load_settings
from src.fable5_os.schemas import GeneratedFile, ValidationIssue
from src.fable5_os.validation import decide_approval
from src.fable5_os.writer import write_files

AGENTS = ["planner", "researcher", "designer", "coder", "validator"]
OUT = {"planner": "plan", "researcher": "research", "designer": "design",
       "coder": "implementation", "validator": "validation"}
REPO = os.path.abspath(os.path.dirname(__file__))


def _new_run_dir() -> str:
    # No Date/random in this context is fine — use pid + monotonic-ish counter.
    base = os.path.join(REPO, "generated")
    os.makedirs(base, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(base, f"swarm-{n:03d}")):
        n += 1
    path = os.path.join(base, f"swarm-{n:03d}")
    os.makedirs(path)
    return path


def _launch_windows(run_dir, py, worker):
    """Open a separate OS terminal window per agent (Windows)."""
    for agent in AGENTS:
        # cmd /k keeps the window open after the agent finishes.
        inner = f'cd /d "{REPO}" && "{py}" "{worker}" {agent} "{run_dir}"'
        cmd = f'start "Fable5: {agent}" cmd /k "{inner}"'
        subprocess.Popen(cmd, shell=True, cwd=REPO)
        time.sleep(0.25)  # slight stagger so windows cascade into view


def _launch_panes(run_dir, py, worker):
    """One Windows Terminal window split into a pane per agent."""
    parts = ["wt"]
    for i, agent in enumerate(AGENTS):
        seg = (["new-tab"] if i == 0 else [";", "split-pane", "-H"])
        seg += ["--title", agent, py, worker, agent, run_dir]
        parts += seg
    subprocess.Popen(parts, cwd=REPO)


def _launch_headless(run_dir, py, worker):
    """No windows — run workers as background processes (for testing)."""
    procs = []
    for agent in AGENTS:
        log = open(os.path.join(run_dir, f"{agent}.log"), "w", encoding="utf-8")
        procs.append(subprocess.Popen([py, worker, agent, run_dir], cwd=REPO,
                                      stdout=log, stderr=subprocess.STDOUT))
    return procs


def main():
    args = [a for a in sys.argv[1:]]
    mode = "windows"
    if "--panes" in args:
        mode = "panes"; args.remove("--panes")
    if "--headless" in args:
        mode = "headless"; args.remove("--headless")
    request = " ".join(args).strip() or "Build a CLI password-strength checker in Python"

    run_dir = _new_run_dir()
    with open(os.path.join(run_dir, "request.txt"), "w", encoding="utf-8") as f:
        f.write(request)

    py = sys.executable
    worker = os.path.join(REPO, "worker.py")

    print("=" * 68)
    print("  FABLE5 SWARM  —  orchestrator overview")
    print("=" * 68)
    print(f"  request:  {request}")
    print(f"  run dir:  {run_dir}")
    print(f"  mode:     {mode}")
    print()

    if mode == "panes" and shutil.which("wt"):
        _launch_panes(run_dir, py, worker)
    elif mode == "headless":
        _launch_headless(run_dir, py, worker)
    else:
        if mode == "panes":
            print("  (Windows Terminal 'wt' not found — opening separate windows instead)")
        _launch_windows(run_dir, py, worker)

    print("  Agent windows launched. Watching for results...\n")

    # Overview: report each agent as its result file appears.
    seen = set()
    order = ["plan", "research", "design", "implementation", "validation"]
    label = {"plan": "🧭 planner", "research": "🔎 researcher", "design": "📐 designer",
             "implementation": "⌨️  coder", "validation": "✅ validator"}
    started = time.time()
    while len(seen) < len(order):
        for key in order:
            if key not in seen and os.path.exists(os.path.join(run_dir, f"{key}.json")):
                seen.add(key)
                print(f"  [{time.time() - started:5.1f}s] {label[key]} finished")
        time.sleep(0.2)
        if time.time() - started > 600:
            print("  timeout waiting for agents.")
            break

    # Write the coder's files to disk.
    impl_path = os.path.join(run_dir, "implementation.json")
    written = []
    if os.path.exists(impl_path):
        impl = json.load(open(impl_path, encoding="utf-8"))
        files = [GeneratedFile.model_validate(x) for x in impl.get("files", [])]
        if files:
            written = write_files(files, os.path.join(run_dir, "output"))

    print("\n" + "=" * 68)
    val_path = os.path.join(run_dir, "validation.json")
    if os.path.exists(val_path):
        val = json.load(open(val_path, encoding="utf-8"))
        # Apply the same strictness gate the orchestrator uses, so the swarm's
        # verdict matches: in 'balanced' only high-severity issues block.
        issues = [ValidationIssue.model_validate(i) for i in val.get("issues", [])]
        approved = decide_approval(val.get("approved", False), issues, load_settings().strictness)
        verdict = "APPROVED" if approved else "NEEDS REVIEW"
        print(f"  Verdict: {verdict}   ({len(issues)} issues)")
    if written:
        print("  Files written:")
        for w in written:
            mark = "ok" if w.get("written") else "FAIL"
            print(f"    [{mark}] {os.path.join(run_dir, 'output', w['path'])}")
    print(f"  Total: {time.time() - started:.1f}s")
    print("=" * 68)


if __name__ == "__main__":
    main()
