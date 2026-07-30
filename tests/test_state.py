import json
import pytest
from theme_compare.models import SemanticError
from theme_compare.state import StateMachine

PHASE_FIELDS = {
    1: "session_and_candidates",
    2: "business_models",
    3: "theme_value_capture",
    4: "competitive_structure",
    5: "financial_conversion",
    6: "valuation_expectations",
    7: "common_scenarios",
    8: "catalysts",
    9: "risks_and_stress",
    10: "final_selection",
}


def initial():
    return {
        "mode": "initial",
        "session_id": "s",
        "generation_id": "g1",
        "active_generation_id": "g1",
        "initial_generation_id": "g1",
        "previous_generation_id": None,
        "generation_history": {"g1": {"candidate_set_id": "cs", "artifacts": []}},
        "candidate_set_id": "cs",
        "comparison_as_of": "2025-01-01T00:00:00Z",
        "source_cutoff_at": "2025-01-01T00:00:00Z",
        "current_phase": 1,
        "completed_phases": [],
        "status": "in_progress",
        "persistence_status": "not_generated",
        "handoff_history": {},
        "active_handoff_id": None,
        "superseded_handoff_ids": [],
    }


def artifact(phase, generation="g1", mode="initial"):
    field = (
        PHASE_FIELDS[phase]
        if mode == "initial"
        else ("update_diff" if phase == 1 else "updated_selection")
    )
    return {
        "mode": mode,
        "phase": phase,
        "generation_id": generation,
        "candidate_set_id": "cs",
        "source_cutoff_at": "2025-01-01T00:00:00Z",
        "facts": [],
        "company_claims": [],
        "external_estimates": [],
        "judgments": [],
        "payload": {field: {}, "summary": "complete"},
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


def test_update_two_phases_preserves_generation(tmp_path):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    state = sm.command("更新", {"generation_id": "g2", "candidate_set_id": "cs"})
    assert (
        set(state["generation_history"]) == {"g1", "g2"}
        and len(state["generation_history"]["g1"]["artifacts"]) == 10
    )
    sm.command("次", artifact(1, "g2", "update"))
    sm.command("次", artifact(2, "g2", "update"))
    assert sm.load()["status"] == "complete"


def test_interrupted_resume_reads_disk(tmp_path):
    sm = machine(tmp_path)
    sm.command("次", artifact(1))
    StateMachine(sm.path).command("次", artifact(2))
    assert StateMachine(sm.path).load()["completed_phases"] == [1, 2]


def test_phase_payload_swap_and_arbitrary_field_rejected(tmp_path):
    bad = artifact(1)
    bad["payload"] = {"common_scenarios": {}, "summary": "wrong"}
    with pytest.raises(SemanticError, match="schema"):
        machine(tmp_path).command("次", bad)
    bad = artifact(1)
    bad["payload"]["unknown"] = 1
    with pytest.raises(SemanticError, match="schema"):
        machine(tmp_path).command("次", bad)


def test_malformed_judgment_rejected(tmp_path):
    bad = artifact(1)
    bad["judgments"] = [{"judgment": "x"}]
    with pytest.raises(SemanticError, match="schema"):
        machine(tmp_path).command("次", bad)
