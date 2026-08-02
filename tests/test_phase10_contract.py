from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_runtime import runtime_artifact, upstream
from theme_compare.api import create_app
from theme_compare.models import SemanticError
from theme_compare.phase2_contract import (
    INITIAL_PHASE10_REQUIREMENT,
    enrich_phase2_contract,
)
from theme_compare.ranking import RANKING_TYPES, derive_rankings, validate_stored_rankings
from theme_compare.storage import JsonVolumeStorage


def _three_candidate_metrics() -> list[dict[str, object]]:
    values = {
        "A": ((0.8, 1.0), (0.7, 2.0)),
        "B": ((0.7, 1.0), (0.7, 2.0)),
        "C": ((0.6, 1.0), (0.6, 2.0)),
    }
    rows: list[dict[str, object]] = []
    for candidate, candidate_values in values.items():
        for ranking_type in RANKING_TYPES:
            for index, (value, weight) in enumerate(candidate_values):
                rows.append(
                    {
                        "candidate_id": candidate,
                        "ranking_type": ranking_type,
                        "value": value,
                        "weight": weight,
                        "effective_weight": weight,
                        "applicable": True,
                        "state": "observed",
                        "comparability": "comparable",
                        "dependency_root": f"{candidate}-{ranking_type}-{index}",
                    }
                )
    return rows


def test_phase10_contract_exposes_exact_derivation_rules():
    contract = enrich_phase2_contract({"mode": "initial", "phase": 10, "phase_requirements": "old"})
    assert contract["phase_requirements"] == INITIAL_PHASE10_REQUIREMENT
    requirement = contract["phase_requirements"]
    for ranking_type in RANKING_TYPES:
        assert ranking_type in requirement
    assert "applicable is true" in requirement
    assert "observed or estimated" in requirement
    assert "comparable or partially_comparable" in requirement
    assert "sum(value * effective_weight) / sum(effective_weight)" in requirement
    assert "score descending" in requirement
    assert "candidate_id ascending" in requirement
    assert "without display rounding" in requirement


def test_three_candidate_five_ranking_exact_scores_and_tie_break():
    rankings, scores = derive_rankings(["C", "B", "A"], _three_candidate_metrics())
    assert set(rankings) == set(RANKING_TYPES)
    assert all(order == ["A", "B", "C"] for order in rankings.values())
    assert scores["tactical"]["A"] == (0.8 + 1.4) / 3.0
    stored = {
        "ordered_candidates": copy.deepcopy(rankings),
        "scores": copy.deepcopy(scores),
    }
    assert (
        validate_stored_rankings(["C", "B", "A"], _three_candidate_metrics(), stored, set())
        == rankings
    )


def test_ranking_diagnostic_supports_exact_repair():
    rankings, scores = derive_rankings(["A", "B", "C"], _three_candidate_metrics())
    stored = {
        "ordered_candidates": copy.deepcopy(rankings),
        "scores": copy.deepcopy(scores),
    }
    stored["ordered_candidates"]["risk_adjusted"] = ["B", "A", "C"]
    stored["scores"]["tactical"]["A"] = round(scores["tactical"]["A"], 3)

    with pytest.raises(SemanticError) as captured:
        validate_stored_rankings(["A", "B", "C"], _three_candidate_metrics(), stored, set())

    message = str(captured.value)
    assert message.startswith("stored ranking or score mismatch: ")
    details = json.loads(message.split(": ", 1)[1])
    assert details["expected_rankings"] == rankings
    assert details["actual_rankings"] == stored["ordered_candidates"]
    assert details["expected_scores"] == scores
    assert details["actual_scores"] == stored["scores"]
    assert details["ranking_mismatches_total"] == 1
    assert details["score_mismatches_total"] == 1
    assert details["diagnostic_limit"] == 50

    repaired = {
        "ordered_candidates": details["expected_rankings"],
        "scores": details["expected_scores"],
    }
    assert (
        validate_stored_rankings(["A", "B", "C"], _three_candidate_metrics(), repaired, set())
        == rankings
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("effective_weight", "effective weight mismatch"),
        ("dependency_root", "double counting dependency root"),
        ("zero_eligible", "eligible metric weight must be positive"),
    ],
)
def test_atomic_metric_integrity_failures_remain_strict(mutation: str, message: str):
    rows = _three_candidate_metrics()
    target = next(
        row for row in rows if row["candidate_id"] == "A" and row["ranking_type"] == "tactical"
    )
    if mutation == "effective_weight":
        target["state"] = "missing"
        target["effective_weight"] = 1.0
    elif mutation == "dependency_root":
        sibling = next(
            row
            for row in rows
            if row is not target
            and row["candidate_id"] == "A"
            and row["ranking_type"] == "tactical"
        )
        sibling["dependency_root"] = target["dependency_root"]
    else:
        for row in rows:
            if row["candidate_id"] == "A" and row["ranking_type"] == "tactical":
                row["applicable"] = False
                row["effective_weight"] = 0.0

    with pytest.raises(SemanticError, match=message):
        derive_rankings(["A", "B", "C"], rows)


def test_phase10_api_rejection_preserves_state_and_expected_maps_repair(tmp_path):
    storage = JsonVolumeStorage(tmp_path)
    client = TestClient(create_app(storage, "secret"))
    headers = {"Authorization": "Bearer secret"}
    session_id = client.post("/v1/sessions", headers=headers, json=upstream()).json()["session_id"]

    for phase in range(1, 10):
        response = client.post(
            f"/v1/sessions/{session_id}/phases",
            headers=headers,
            json=runtime_artifact(phase),
        )
        assert response.status_code == 200, response.json()

    contract = client.get(f"/v1/sessions/{session_id}/next-contract", headers=headers).json()
    assert contract["phase"] == 10
    assert contract["phase_requirements"] == INITIAL_PHASE10_REQUIREMENT

    bad = runtime_artifact(10)
    selection = bad["payload"]["final_selection"]
    tactical = next(
        row for row in selection["atomic_ranking_metrics"] if row["ranking_type"] == "tactical"
    )
    tactical["value"] = 0.5333333333333333
    selection["stored_scores"]["tactical"]["A"] = 0.533

    before = storage.path(session_id).read_bytes()
    rejected = client.post(f"/v1/sessions/{session_id}/phases", headers=headers, json=bad)
    error = rejected.json()["error"]
    assert rejected.status_code == 422
    assert error["retryable"] is True
    assert error["terminal"] is False
    assert error["state_unchanged"] is True
    assert storage.path(session_id).read_bytes() == before

    summary = client.get(f"/v1/sessions/{session_id}", headers=headers).json()
    assert summary["current_phase"] == 10
    assert summary["completed_phases"] == list(range(1, 10))

    details = json.loads(error["message"].split(": ", 1)[1])
    selection["stored_rankings"] = details["expected_rankings"]
    selection["stored_scores"] = details["expected_scores"]
    accepted = client.post(f"/v1/sessions/{session_id}/phases", headers=headers, json=bad)
    assert accepted.status_code == 200, accepted.json()
    assert accepted.json()["status"] == "complete"
    assert accepted.json()["active_handoff"]["handoff_id"] == "h1"
