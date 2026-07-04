from src.fable5_os.agents import AgentRunner
from src.fable5_os.config import Settings
from src.fable5_os.orchestrator import Fable5Orchestrator
from src.fable5_os.run_agentic_os import run_demo
from src.fable5_os.schemas import CoderOutput, GeneratedFile, PlannerOutput, ValidationIssue
from src.fable5_os.validation import check_code, decide_approval, has_blocking_issues, is_blocked
from src.fable5_os.workflow import build_workflow
from src.fable5_os.writer import UnsafePathError, write_files


def _offline_runner() -> AgentRunner:
    return AgentRunner(Settings(force_offline=True))


def test_workflow_runs() -> None:
    result = run_demo("Build an agentic OS")
    assert "request" in result
    assert "workflow" in result
    assert isinstance(result["workflow"], list)
    # Every stage should be populated by the pipeline.
    for key in ("plan", "research", "design", "implementation", "validation"):
        assert result.get(key), f"missing stage: {key}"


def test_orchestrator_returns_structured_result() -> None:
    orchestrator = Fable5Orchestrator(settings=Settings(force_offline=True))
    result = orchestrator.run("Ship a safer multi-agent system")
    assert result["plan"]["goal"]
    assert isinstance(result["approved"], bool)
    assert "validator: self-check and verdict" in result["workflow"]


def test_agent_runner_offline_returns_valid_schema() -> None:
    runner = _offline_runner()
    plan = runner.run("planner", "Do a thing")
    assert isinstance(plan, PlannerOutput)
    assert plan.steps  # offline planner always yields concrete steps


def test_deterministic_validation_flags_missing_verification() -> None:
    bad = CoderOutput(approach="do it", files=[], verification=[], confidence=0.5)
    issues = check_code(bad)
    assert has_blocking_issues(issues)


def test_agent_runner_fires_hooks() -> None:
    runner = _offline_runner()
    events = []
    runner.on_agent_start = lambda name: events.append(("start", name))
    runner.on_agent_end = lambda name, fb: events.append(("end", name, fb))
    runner.run("planner", "do a thing")
    assert ("start", "planner") in events
    # offline always falls back, so end reports used_fallback=True
    assert ("end", "planner", True) in events


def test_per_agent_model_resolution() -> None:
    s = Settings(model="cheap-default", agent_models={"coder": "big-model"})
    assert s.model_for("planner") == "cheap-default"   # falls back to default
    assert s.model_for("coder") == "big-model"          # per-agent override wins


def test_parallel_and_sequential_both_complete() -> None:
    runner = _offline_runner()
    for parallel in (True, False):
        app = build_workflow(runner, parallel=parallel)
        state = app.invoke(
            {"request": "parallel test"},
            config={"configurable": {"thread_id": f"par-{parallel}"}},
        )
        # Both flows must populate every stage; the coder fans in from both.
        for key in ("plan", "research", "design", "implementation", "validation"):
            assert state.get(key), f"{key} missing (parallel={parallel})"


def test_ponytail_behavior_injected_for_build_agents() -> None:
    from src.fable5_os.prompts import system_prompt_for

    coder = system_prompt_for("coder", behavior="ponytail")
    assert "lazy senior developer" in coder.lower()
    assert "ponytail:" in coder  # the shortcut-comment convention
    # Researcher is not a build agent; it stays clean.
    assert "lazy senior developer" not in system_prompt_for("researcher", behavior="ponytail").lower()
    # Toggle off removes it entirely.
    assert "lazy senior developer" not in system_prompt_for("coder", behavior="none").lower()


def test_coder_offline_emits_real_files() -> None:
    runner = _offline_runner()
    code = runner.run("coder", "make a thing")
    assert isinstance(code, CoderOutput)
    assert code.files, "offline coder should emit at least one file"
    assert any(f.path == "main.py" and f.content.strip() for f in code.files)


def test_writer_writes_files_and_blocks_escape(tmp_path) -> None:
    files = [
        GeneratedFile(path="app/main.py", content="print('hi')\n", description="entry"),
        GeneratedFile(path="../evil.py", content="x=1", description="escape attempt"),
        GeneratedFile(path="/abs.py", content="x=1", description="absolute attempt"),
    ]
    results = write_files(files, str(tmp_path / "out"))
    by_path = {r["path"]: r for r in results}
    assert by_path["app/main.py"]["written"] is True
    assert (tmp_path / "out" / "app" / "main.py").read_text() == "print('hi')\n"
    # Both traversal attempts are rejected, not written.
    assert all(not r["written"] for r in results if r["path"] in {"../evil.py", "/abs.py"})
    assert not (tmp_path / "evil.py").exists()


def test_strictness_gate() -> None:
    med = [ValidationIssue(stage="code", problem="x", severity="medium")]
    high = [ValidationIssue(stage="code", problem="y", severity="high")]
    # balanced: medium does not block; high does
    assert not is_blocked(med, "balanced")
    assert is_blocked(high, "balanced")
    # strict: medium blocks, and the model must also approve
    assert is_blocked(med, "strict")
    assert decide_approval(True, med, "balanced") is True
    assert decide_approval(True, med, "strict") is False
    # lenient/balanced: an overly-cautious model verdict cannot veto a clean run
    assert decide_approval(False, [], "balanced") is True


def test_workflow_loops_back_on_blocking_issues(monkeypatch) -> None:
    """A blocking validation issue should trigger at least one revision."""

    runner = _offline_runner()
    real_run = runner.run

    def patched(agent_name, request, context=None):
        out = real_run(agent_name, request, context)
        # Force the coder to omit verification -> deterministic high-severity issue.
        if agent_name == "coder":
            return out.model_copy(update={"verification": []})
        return out

    monkeypatch.setattr(runner, "run", patched)
    app = build_workflow(runner, max_revisions=1)
    state = app.invoke(
        {"request": "loop test"},
        config={"configurable": {"thread_id": "loop-test"}},
    )
    assert state["revision"] == 1
    assert any(i["severity"] == "high" for i in state["issues"])
