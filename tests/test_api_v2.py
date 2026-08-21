from __future__ import annotations

from fastapi.testclient import TestClient
from phase_fixtures import CANDIDATE

from theme_compare.api import create_app
from theme_compare.storage import JsonVolumeStorage


def create_body():
    return {
        "contract_version": "2.0.0",
        "mode": "standalone",
        "theme": "power-infrastructure",
        "analysis_as_of": "2026-08-21T00:00:00Z",
        "source_cutoff_at": "2026-08-20T23:00:00Z",
        "candidates": [CANDIDATE],
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


def test_v2_create_requires_and_replays_query_idempotency_key(tmp_path):
    client = TestClient(create_app(JsonVolumeStorage(tmp_path), "secret"))
    auth = {"Authorization": "Bearer secret"}
    body = create_body()

    missing = client.post("/v2/sessions", headers=auth, json=body)
    assert missing.status_code == 422

    url = "/v2/sessions?idempotency_key=create-request-0001"
    first = client.post(url, headers=auth, json=body)
    second = client.post(url, headers=auth, json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["session_id"] == second.json()["session_id"]
    sid = first.json()["session_id"]
    next_contract = client.get(f"/v2/sessions/{sid}/next-contract", headers=auth)
    assert next_contract.status_code == 200
    assert next_contract.json()["phase"] == 1


def test_v2_keeps_header_idempotency_key_compatibility(tmp_path):
    client = TestClient(create_app(JsonVolumeStorage(tmp_path), "secret"))
    headers = {
        "Authorization": "Bearer secret",
        "Idempotency-Key": "legacy-header-0001",
    }
    response = client.post("/v2/sessions", headers=headers, json=create_body())
    assert response.status_code == 200


def test_v2_rejects_conflicting_query_and_header_idempotency_keys(tmp_path):
    client = TestClient(create_app(JsonVolumeStorage(tmp_path), "secret"))
    headers = {
        "Authorization": "Bearer secret",
        "Idempotency-Key": "header-key-0001",
    }
    response = client.post(
        "/v2/sessions?idempotency_key=query-key-0001",
        headers=headers,
        json=create_body(),
    )
    assert response.status_code == 422
    assert "conflicting idempotency keys" in response.json()["error"]["message"]


def test_v2_rejects_idempotency_key_reuse_with_different_payload(tmp_path):
    client = TestClient(create_app(JsonVolumeStorage(tmp_path), "secret"))
    url = "/v2/sessions?idempotency_key=create-request-0002"
    headers = {"Authorization": "Bearer secret"}
    first = client.post(url, headers=headers, json=create_body())
    assert first.status_code == 200

    changed = create_body()
    changed["theme"] = "different-theme"
    replay = client.post(url, headers=headers, json=changed)
    assert replay.status_code == 422
    assert replay.json()["error"]["category"] == "validation_transition"
