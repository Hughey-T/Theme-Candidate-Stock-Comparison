from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
from phase_fixtures import CANDIDATE

from theme_compare.api import create_app
from theme_compare.storage import JsonVolumeStorage
from theme_compare.v2_runtime import V2RuntimeService


def _candidate(candidate_id: str) -> dict:
    row = deepcopy(CANDIDATE)
    row["candidate_id"] = candidate_id
    row["issuer_id"] = f"issuer-{candidate_id}"
    row["issuer_name"] = candidate_id
    row["ticker"] = candidate_id
    return row


def _create_body() -> dict:
    return {
        "contract_version": "2.0.0",
        "mode": "standalone",
        "theme": "power-infrastructure",
        "analysis_as_of": "2026-08-21T00:00:00Z",
        "source_cutoff_at": "2026-08-20T23:00:00Z",
        "candidates": [_candidate("A"), _candidate("B")],
        "horizons": [
            {
                "horizon_id": "medium",
                "minimum_months": 12,
                "maximum_months": 24,
                "benchmark": "SPY",
                "required_return": 0.1,
            }
        ],
    }


def _phase11_client(tmp_path: Path) -> tuple[TestClient, V2RuntimeService, str]:
    storage = JsonVolumeStorage(tmp_path)
    client = TestClient(create_app(storage, "secret"))
    response = client.post(
        "/v2/sessions?idempotency_key=create-phase11-test-0001",
        headers={"Authorization": "Bearer secret"},
        json=_create_body(),
    )
    assert response.status_code == 200
    sid = response.json()["session_id"]

    service = V2RuntimeService(storage)
    state = service._load(sid)
    state["phase"] = 11
    state["independent_ai_frozen"] = True
    state["independent_ai_hash"] = service._hash({"medium": []})
    service._write(sid, state)
    return client, service, sid


def _rankings() -> dict:
    return {
        "evidence_only_mechanical": {"inputs": [{"classification": "FACTS"}]},
        "scenario_derived": {"inputs": [{"classification": "AI_ASSUMPTIONS"}]},
    }


def test_phase11_contract_names_required_pairwise_fields(tmp_path: Path) -> None:
    _client, service, sid = _phase11_client(tmp_path)

    requirements = service.contract(sid)["submission_requirements"]

    assert requirements["pairwise_record_fields"] == ["candidate_a", "candidate_b"]
    assert "candidate_a and candidate_b" in requirements["pairwise_requirement"]


def test_phase11_missing_candidate_a_returns_structured_422_and_preserves_state(
    tmp_path: Path,
) -> None:
    client, service, sid = _phase11_client(tmp_path)
    artifact = {
        "generation_id": "g1",
        "phase": 11,
        "information": [],
        "payload": {
            "rankings": _rankings(),
            "deep_candidates": ["A", "B"],
            "pairwise": [{"candidate_b": "B"}],
        },
    }

    response = client.post(
        f"/v2/sessions/{sid}/phases?idempotency_key=phase11-malformed-0001",
        headers={"Authorization": "Bearer secret"},
        json=artifact,
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["category"] == "validation_transition"
    assert error["state_unchanged"] is True
    assert "candidate_a" in error["message"]
    persisted = service._load(sid)
    assert persisted["phase"] == 11
    assert persisted["artifacts"] == []


def test_phase11_duplicate_unordered_pair_returns_422(tmp_path: Path) -> None:
    client, _service, sid = _phase11_client(tmp_path)
    artifact = {
        "generation_id": "g1",
        "phase": 11,
        "information": [],
        "payload": {
            "rankings": _rankings(),
            "deep_candidates": ["A", "B"],
            "pairwise": [
                {"candidate_a": "A", "candidate_b": "B"},
                {"candidate_a": "B", "candidate_b": "A"},
            ],
        },
    }

    response = client.post(
        f"/v2/sessions/{sid}/phases?idempotency_key=phase11-duplicate-0001",
        headers={"Authorization": "Bearer secret"},
        json=artifact,
    )

    assert response.status_code == 422
    assert "duplicate unordered pair coverage" in response.json()["error"]["message"]
