from __future__ import annotations

import copy
import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from phase_fixtures import artifact
from test_runtime import runtime_artifact, upstream
from theme_compare.api import create_app
from theme_compare.models import SemanticError
from theme_compare.phase2_contract import (
    INITIAL_PHASE2_REQUIREMENT,
    enrich_phase2_contract,
    rewrite_phase2_validation_error,
)
from theme_compare.storage import JsonVolumeStorage


def _phase2_for_two_candidates():
    item = artifact(2)
    payload = item["payload"]["business_models"]
    first = payload["candidates"][0]
    second = copy.deepcopy(first)
    second["candidate_id"] = "B"
    second["primary_metric"] = "EBITDA"
    second["secondary_metric"] = "revenue"
    payload["candidates"] = [first, second]
    payload["detailed_candidates"] = ["A", "B"]
    return item


def test_enrich_phase2_contract_only_changes_initial_phase2():
    phase2 = enrich_phase2_contract({"mode": "initial", "phase": 2, "phase_requirements": "old"})
    assert phase2["phase_requirements"] == INITIAL_PHASE2_REQUIREMENT
    assert "unordered candidate pair" in phase2["phase_requirements"]
    assert "combination(candidate_count, 2)" in phase2["phase_requirements"]

    other = {"mode": "initial", "phase": 3, "phase_requirements": "unchanged"}
    assert enrich_phase2_contract(other) == other


def test_metric_diagnostic_is_sorted_and_bounded():
    item = _phase2_for_two_candidates()
    payload = item["payload"]["business_models"]
    payload["comparability_matrix"] = [
        {
            "left_candidate_id": "A",
            "right_candidate_id": "B",
            "metric": "unknown",
            "comparability": "reference_only",
        }
    ]
    rewritten = rewrite_phase2_validation_error(
        SemanticError("comparability matrix unknown or missing metric"), item
    )
    message = str(rewritten)
    assert message.startswith("comparability matrix metric vocabulary mismatch: ")
    details = json.loads(message.split(": ", 1)[1])
    assert details["expected_metrics"] == ["EBITDA", "FCF", "revenue"]
    assert details["actual_metrics"] == ["unknown"]
    assert details["missing_metrics"] == ["EBITDA", "FCF", "revenue"]
    assert details["extra_metrics"] == ["unknown"]
    assert details["diagnostic_limit"] == 20


def test_pair_metric_coverage_diagnostic_counts_missing_rows():
    item = _phase2_for_two_candidates()
    payload = item["payload"]["business_models"]
    payload["comparability_matrix"] = [
        {
            "left_candidate_id": "A",
            "right_candidate_id": "B",
            "metric": "FCF",
            "comparability": "reference_only",
        }
    ]
    rewritten = rewrite_phase2_validation_error(
        SemanticError("comparability matrix pair/metric coverage mismatch"), item
    )
    details = json.loads(str(rewritten).split(": ", 1)[1])
    assert details["expected_count"] == 3
    assert details["actual_count"] == 1
    assert details["missing_pair_metrics_total"] == 2
    assert details["extra_pair_metrics_total"] == 0


def test_action_contract_and_retryable_phase2_error_leave_state_unchanged(tmp_path):
    client = TestClient(create_app(JsonVolumeStorage(tmp_path), "secret"))
    headers = {"Authorization": "Bearer secret"}
    session_id = client.post("/v1/sessions", headers=headers, json=upstream()).json()["session_id"]
    accepted = client.post(
        f"/v1/sessions/{session_id}/phases",
        headers=headers,
        json=runtime_artifact(1),
    )
    assert accepted.status_code == 200

    contract = client.get(
        f"/v1/sessions/{session_id}/next-contract", headers=headers
    ).json()
    assert contract["phase"] == 2
    assert "unique union" in contract["phase_requirements"]
    assert "unordered candidate pair" in contract["phase_requirements"]

    bad = _phase2_for_two_candidates()
    bad["payload"]["business_models"]["comparability_matrix"] = [
        {
            "left_candidate_id": "A",
            "right_candidate_id": "B",
            "metric": "unknown",
            "comparability": "reference_only",
        }
    ]
    before = (tmp_path / f"{session_id}.json").read_bytes()
    response = client.post(
        f"/v1/sessions/{session_id}/phases", headers=headers, json=bad
    )
    error = response.json()["error"]
    assert response.status_code == 422
    assert error["retryable"] is True
    assert error["terminal"] is False
    assert error["state_unchanged"] is True
    assert "expected_metrics" in error["message"]
    assert (tmp_path / f"{session_id}.json").read_bytes() == before
    summary = client.get(f"/v1/sessions/{session_id}", headers=headers).json()
    assert summary["current_phase"] == 2
    assert summary["completed_phases"] == [1]
