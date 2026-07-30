import json

import pytest

from theme_compare.models import SemanticError
from theme_compare.state import StateMachine


def initial():
    return {
        "mode": "initial",
        "session_id": "s",
        "generation_id": "g1",
        "candidate_set_id": "cs",
        "comparison_as_of": "2025-01-01T00:00:00Z",
        "source_cutoff_at": "2025-01-01T00:00:00Z",
        "current_phase": 1,
        "completed_phases": [],
        "status": "in_progress",
        "persistence_status": "not_generated",
        "artifacts": [],
    }


def artifact(phase, generation="g1"):
    return {
        "phase": phase,
        "generation_id": generation,
        "candidate_set_id": "cs",
        "source_cutoff_at": "2025-01-01T00:00:00Z",
    }


def machine(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps(initial()))
    return StateMachine(path)


def test_initial_ten_phases_and_idempotency_guard(tmp_path):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    assert sm.load()["status"] == "complete"
    with pytest.raises(SemanticError):
        sm.command("次", artifact(10))


@pytest.mark.parametrize("operation,phase", [("次", 2), ("bad", 1), ("更新", 1)])
def test_invalid_transition(tmp_path, operation, phase):
    with pytest.raises(SemanticError):
        machine(tmp_path).command(operation, artifact(phase))


def test_update_two_phases(tmp_path):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    state = sm.command("更新", {"generation_id": "g2", "candidate_set_id": "cs"})
    assert state["mode"] == "update"
    sm.command("次", artifact(1, "g2"))
    sm.command("次", artifact(2, "g2"))
    assert sm.load()["status"] == "complete"


def test_interrupted_resume_reads_disk(tmp_path):
    sm = machine(tmp_path)
    sm.command("次", artifact(1))
    StateMachine(sm.path).command("次", artifact(2))
    assert StateMachine(sm.path).load()["completed_phases"] == [1, 2]
