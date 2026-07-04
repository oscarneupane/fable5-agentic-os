from src.fable5_os.config import Settings
from src.fable5_os.orchestrator import Fable5Orchestrator


def _offline_orchestrator() -> Fable5Orchestrator:
    # Force offline so tests are deterministic and never hit the network.
    return Fable5Orchestrator(settings=Settings(force_offline=True))


def test_orchestrator_runs() -> None:
    orchestrator = _offline_orchestrator()
    result = orchestrator.run("Test request")
    assert result["message"] == "Fable5 orchestrator completed the request."
    assert "fable5" in result["agents"]
    assert isinstance(orchestrator.plan_workflow("Test request"), list)


def test_offline_mode_is_reported() -> None:
    orchestrator = _offline_orchestrator()
    assert orchestrator.mode == "offline"
    result = orchestrator.run("Anything")
    assert result["mode"] == "offline"


def test_empty_request_is_rejected() -> None:
    orchestrator = _offline_orchestrator()
    for bad in ["", "   "]:
        try:
            orchestrator.run(bad)
        except ValueError:
            continue
        raise AssertionError("empty request should raise ValueError")
