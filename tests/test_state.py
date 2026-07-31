import json
import pytest
from theme_compare.models import SemanticError
from theme_compare.state import StateMachine

from phase_fixtures import SET_ID, TS, artifact


def initial():
    return {
        "mode": "initial",
        "session_id": "s",
        "generation_id": "g1",
        "active_generation_id": "g1",
        "initial_generation_id": "g1",
        "previous_generation_id": None,
        "generation_history": {
            "g1": {
                "candidate_set_id": SET_ID,
                "comparison_as_of": TS,
                "source_cutoff_at": TS,
                "detailed_candidates": [],
                "artifacts": [],
            }
        },
        "candidate_set_id": SET_ID,
        "comparison_as_of": TS,
        "source_cutoff_at": TS,
        "current_phase": 1,
        "completed_phases": [],
        "status": "in_progress",
        "persistence_status": "not_generated",
        "handoff_history": {},
        "active_handoff_id": None,
        "superseded_handoff_ids": [],
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


def test_initial_handoff_projects_validated_phase_artifacts(tmp_path):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    handoff = sm.load()["handoff_history"]["h1"]
    assert handoff["valuation_ranges"]["A"]["current_multiple"] == 10
    assert handoff["valuation_ranges"]["A"]["state"] == "observed"
    assert handoff["catalysts"]["A"] == ["earnings"]
    assert "loss" in handoff["company_specific_risks"]["A"]
    assert handoff["thesis_invalidation_conditions"]["A"] == ["demand"]
    assert handoff["evidence_manifest"] == ["E1", "E2"]
    assert handoff["confidence"]["A"] == "medium"
    assert handoff["key_assumptions"] == ["demand persists"]


def test_update_projection_adds_explicit_state_and_removes_absent_candidate(tmp_path):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    state = sm.load()
    update = artifact(1, "g2", "update", "2025-01-31T00:00:00Z")
    changes = update["payload"]["update_diff"]["handoff_context_changes"]
    added = json.loads(json.dumps(changes["candidate_changes"][0]))
    added["candidate_id"] = "B"
    added["valuation"].update(
        state="not_evaluable",
        data_state="not_evaluable",
        method=None,
        current_multiple=None,
        implied_growth=None,
        implied_margin=None,
    )
    added["catalysts"] = {"state": "no_identified_catalyst", "values": []}
    for key in ("company_specific_risks", "thesis_invalidation_conditions"):
        added[key] = {"state": "not_evaluable", "values": []}
    added["confidence"] = {"state": "not_evaluable", "value": None}
    added["evidence_refs"] = {"state": "not_evaluable", "values": []}
    added["assumptions"] = {"state": "not_evaluable", "values": []}
    changes["candidate_changes"] = [added]
    state.update(mode="update", active_generation_id="g2", generation_id="g2")
    state["generation_history"]["g2"] = {
        "candidate_set_id": SET_ID,
        "comparison_as_of": "2025-02-01T00:00:00Z",
        "source_cutoff_at": "2025-01-31T00:00:00Z",
        "detailed_candidates": ["B"],
        "artifacts": [update],
    }
    projected = sm._project_handoff_context(state, ["B"])
    assert set(projected["valuation_ranges"]) == {"B"}
    assert projected["valuation_ranges"]["B"]["state"] == "not_evaluable"
    assert projected["valuation_ranges"]["B"]["current_multiple"] is None
    assert projected["catalysts"]["B"] == ["no_identified_catalyst"]


@pytest.mark.parametrize("operation,phase", [("次", 2), ("bad", 1), ("更新", 1)])
def test_invalid_transition(tmp_path, operation, phase):
    with pytest.raises(SemanticError):
        machine(tmp_path).command(operation, artifact(phase))


def test_update_two_phases_preserves_generation(tmp_path):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    state = sm.command(
        "更新",
        {
            "new_generation_id": "g2",
            "new_candidate_set_id": SET_ID,
            "new_comparison_as_of": "2025-02-01T00:00:00Z",
            "new_source_cutoff_at": "2025-01-31T00:00:00Z",
            "previous_generation_id": "g1",
        },
    )
    assert (
        set(state["generation_history"]) == {"g1", "g2"}
        and len(state["generation_history"]["g1"]["artifacts"]) == 10
    )
    sm.command("次", artifact(1, "g2", "update", "2025-01-31T00:00:00Z"))
    sm.command("次", artifact(2, "g2", "update", "2025-01-31T00:00:00Z"))
    completed = sm.load()
    assert completed["status"] == "complete"
    assert completed["active_handoff_id"] == "h2"
    assert completed["handoff_history"]["h1"]["status"] == "superseded"
    assert completed["handoff_history"]["h1"]["superseded_by"] == "h2"
    assert completed["handoff_history"]["h2"]["status"] == "active"
    assert completed["superseded_handoff_ids"] == ["h1"]
    assert completed["handoff_history"]["h2"]["valuation_ranges"]["A"]["current_multiple"] == 12
    assert completed["handoff_history"]["h2"]["catalysts"]["A"] == ["product launch"]
    assert completed["handoff_history"]["h2"]["company_specific_risks"]["A"] == ["execution"]
    assert completed["handoff_history"]["h2"]["thesis_invalidation_conditions"]["A"] == [
        "launch failure"
    ]
    assert completed["handoff_history"]["h2"]["confidence"]["A"] == "high"
    assert completed["handoff_history"]["h2"]["evidence_manifest"] == ["E1"]


def test_two_consecutive_update_generations_complete_and_chain_handoffs(tmp_path):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    sm.command(
        "更新",
        {
            "new_generation_id": "g2",
            "new_candidate_set_id": SET_ID,
            "new_comparison_as_of": "2025-02-01T00:00:00Z",
            "new_source_cutoff_at": "2025-01-31T00:00:00Z",
            "previous_generation_id": "g1",
        },
    )
    sm.command("次", artifact(1, "g2", "update", "2025-01-31T00:00:00Z"))
    sm.command("次", artifact(2, "g2", "update", "2025-01-31T00:00:00Z"))
    sm.command(
        "更新",
        {
            "new_generation_id": "g3",
            "new_candidate_set_id": SET_ID,
            "new_comparison_as_of": "2025-03-01T00:00:00Z",
            "new_source_cutoff_at": "2025-02-28T00:00:00Z",
            "previous_generation_id": "g2",
        },
    )
    sm.command("次", artifact(1, "g3", "update", "2025-02-28T00:00:00Z"))
    sm.command("次", artifact(2, "g3", "update", "2025-02-28T00:00:00Z"))
    state = sm.load()
    assert set(state["generation_history"]) == {"g1", "g2", "g3"}
    assert state["active_generation_id"] == "g3" and state["active_handoff_id"] == "h3"
    assert state["superseded_handoff_ids"] == ["h1", "h2"]
    assert state["handoff_history"]["h2"]["superseded_by"] == "h3"
    assert state["handoff_history"]["h3"]["valuation_ranges"]["A"]["current_multiple"] == 12
    assert state["handoff_history"]["h3"]["catalysts"]["A"] == ["product launch"]
    assert state["handoff_history"]["h3"]["company_specific_risks"]["A"] == ["execution"]


@pytest.mark.parametrize(
    "mutation",
    [
        "same_generation",
        "stale_cutoff",
        "same_instant_offset",
        "past_cutoff",
        "future_cutoff",
        "old_comparison",
    ],
)
def test_update_start_contract_rejects_invalid_metadata(tmp_path, mutation):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    metadata = {
        "new_generation_id": "g2",
        "new_candidate_set_id": SET_ID,
        "new_comparison_as_of": "2025-02-01T00:00:00Z",
        "new_source_cutoff_at": "2025-01-31T00:00:00Z",
        "previous_generation_id": "g1",
    }
    if mutation == "same_generation":
        metadata["new_generation_id"] = "g1"
    elif mutation == "stale_cutoff":
        metadata["new_source_cutoff_at"] = TS
    elif mutation == "same_instant_offset":
        metadata["new_source_cutoff_at"] = "2025-01-01T09:00:00+09:00"
    elif mutation == "past_cutoff":
        metadata["new_source_cutoff_at"] = "2024-12-31T23:59:59Z"
    elif mutation == "future_cutoff":
        metadata["new_source_cutoff_at"] = "2025-03-01T00:00:00Z"
    else:
        metadata["new_comparison_as_of"] = "2024-12-01T00:00:00Z"
    with pytest.raises(SemanticError):
        sm.command("更新", metadata)


def test_update_cutoff_one_second_later_is_accepted(tmp_path):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    state = sm.command(
        "更新",
        {
            "new_generation_id": "g2",
            "new_candidate_set_id": SET_ID,
            "new_comparison_as_of": "2025-02-01T00:00:00Z",
            "new_source_cutoff_at": "2025-01-01T00:00:01Z",
            "previous_generation_id": "g1",
        },
    )
    assert state["active_generation_id"] == "g2"


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


@pytest.mark.parametrize("field", ["theme_purity", "theme_sensitivity", "value_capture"])
def test_phase_candidate_coverage_rejected(tmp_path, field):
    sm = machine(tmp_path)
    sm.command("次", artifact(1))
    sm.command("次", artifact(2))
    bad = artifact(3)
    bad["payload"]["theme_value_capture"][field].append(
        dict(bad["payload"]["theme_value_capture"][field][0])
    )
    with pytest.raises(SemanticError, match="coverage"):
        sm.command("次", bad)


@pytest.mark.parametrize(
    "mutation", ["duplicate_reverse", "missing_metric", "unknown_metric", "self_pair"]
)
def test_comparability_matrix_contract_rejected(tmp_path, mutation):
    sm = machine(tmp_path)
    sm.command("次", artifact(1))
    bad = artifact(2)
    value = bad["payload"]["business_models"]
    second = dict(value["candidates"][0])
    second.update(candidate_id="B")
    value["candidates"].append(second)
    value["detailed_candidates"].append("B")
    value["comparability_matrix"] = [
        {
            "left_candidate_id": "A",
            "right_candidate_id": "B",
            "metric": metric,
            "comparability": "comparable",
        }
        for metric in ("FCF", "revenue")
    ]
    if mutation == "duplicate_reverse":
        value["comparability_matrix"].append(
            {
                "left_candidate_id": "B",
                "right_candidate_id": "A",
                "metric": "FCF",
                "comparability": "not_comparable",
            }
        )
    elif mutation == "missing_metric":
        value["comparability_matrix"].pop()
    elif mutation == "unknown_metric":
        value["comparability_matrix"][0]["metric"] = "unknown"
    else:
        value["comparability_matrix"][0].update(right_candidate_id="A")
    with pytest.raises(SemanticError):
        sm.command("次", bad)


@pytest.mark.parametrize("mutation", ["artifact_generation", "artifact_cutoff", "candidate_set"])
def test_old_generation_history_tampering_rejected(tmp_path, mutation):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    state = json.loads(sm.path.read_text())
    if mutation == "artifact_generation":
        state["generation_history"]["g1"]["artifacts"][0]["generation_id"] = "tampered"
    elif mutation == "artifact_cutoff":
        state["generation_history"]["g1"]["artifacts"][0]["source_cutoff_at"] = (
            "2024-12-31T00:00:00Z"
        )
    else:
        state["generation_history"]["g1"]["candidate_set_id"] = "tampered"
    sm.path.write_text(json.dumps(state))
    with pytest.raises(SemanticError):
        sm.load()


def test_payload_evidence_reference_uses_generation_registry(tmp_path):
    sm = machine(tmp_path)
    sm.command("次", artifact(1))
    sm.command("次", artifact(2))
    bad = artifact(3)
    bad["payload"]["theme_value_capture"]["theme_purity"][0]["evidence_refs"] = ["UNKNOWN"]
    with pytest.raises(SemanticError, match="evidence"):
        sm.command("次", bad)


def test_previous_update_semantic_tampering_is_detected_with_later_generation(tmp_path):
    sm = machine(tmp_path)
    for phase in range(1, 11):
        sm.command("次", artifact(phase))
    for generation, previous, comparison, cutoff in (
        ("g2", "g1", "2025-02-01T00:00:00Z", "2025-01-31T00:00:00Z"),
        ("g3", "g2", "2025-03-01T00:00:00Z", "2025-02-28T00:00:00Z"),
    ):
        sm.command(
            "更新",
            {
                "new_generation_id": generation,
                "new_candidate_set_id": SET_ID,
                "new_comparison_as_of": comparison,
                "new_source_cutoff_at": cutoff,
                "previous_generation_id": previous,
            },
        )
        sm.command("次", artifact(1, generation, "update", cutoff))
        sm.command("次", artifact(2, generation, "update", cutoff))
    state = json.loads(sm.path.read_text())
    state["generation_history"]["g2"]["artifacts"][1]["payload"]["updated_selection"][
        "scenario_results"
    ][0]["probability_weighted_annualized_return"] += 0.1
    sm.path.write_text(json.dumps(state))
    with pytest.raises(SemanticError):
        sm.load()
