from __future__ import annotations

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
    rewrite_phase2_validation_error,
)
from theme_compare.storage import JsonVolumeStorage


def test_phase10_contract_requires_complete_hard_gate_map():
    contract = enrich_phase2_contract(
        {"mode": "initial", "phase": 10, "phase_requirements": "old"}
    )
    requirement = contract["phase_requirements"]
    assert requirement == INITIAL_PHASE10_REQUIREMENT
    assert "key set exactly equals candidate_ids" in requirement
    assert "empty array" in requirement
    assert "empty hard_gates object" in requirement
    assert "missing candidate keys" in requirement
    assert "extra candidate keys" in requirement


def test_empty_hard_gate_map_returns_bounded_repair_diagnostic():
    artifact = runtime_artifact(10)
    artifact["payload"]["final_selection"]["hard_gates"] = {}

    rewritten = rewrite_phase2_validation_error(
        SemanticError("phase-artifact schema violation"), artifact
    )
    message = str(rewritten)
    assert message.startswith("Phase 10 hard_gates contract mismatch: ")
    details = json.loads(message.split(": ", 1)[1])
    assert details["expected_candidates"] == ["A"]
    assert details["actual_candidates"] == []
    assert details["missing_candidates"] == ["A"]
    assert details["extra_candidates"] == []
    assert details["expected_hard_gates"] == {"A": []}
    assert details["diagnostic_limit"] == 20


def test_valid_hard_gate_map_does_not_mask_unrelated_error():
    artifact = runtime_artifact(10)
    original = SemanticError("unrelated Phase 10 error")
    assert rewrite_phase2_validation_error(original, artifact) is original


def test_phase10_empty_hard_gates_rejection_preserves_state_and_repair_completes(tmp_path):
    storage = JsonVolumeStorage(tmp_path)
    client = TestClient(create_app(storage, "secret"))
    headers = {"Authorization": "Bearer secret"}
    session_id = client.post("/v1/sessions", headers=headers, json=upstream()).json()[
        "session_id"
    ]

    for phase in range(1, 10):
        response = client.post(
            f"/v1/sessions/{session_id}/phases",
            headers=headers,
            json=runtime_artifact(phase),
        )
        assert response.status_code == 200, response.json()

    bad = runtime_artifact(10)
    bad["payload"]["final_selection"]["hard_gates"] = {}
    before = storage.path(session_id).read_bytes()

    rejected = client.post(
        f"/v1/sessions/{session_id}/phases", headers=headers, json=bad
    )
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
    bad["payload"]["final_selection"]["hard_gates"] = details[
        "expected_hard_gates"
    ]
    accepted = client.post(
        f"/v1/sessions/{session_id}/phases", headers=headers, json=bad
    )
    assert accepted.status_code == 200, accepted.json()
    assert accepted.json()["status"] == "complete"
    assert accepted.json()["active_handoff"]["handoff_id"] == "h1"
