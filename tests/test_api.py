from __future__ import annotations
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_runtime import runtime_artifact, upstream
from theme_compare.api import create_app
from theme_compare.storage import JsonVolumeStorage


def client(tmp_path, key="secret"):
    return TestClient(create_app(JsonVolumeStorage(tmp_path), key))


def test_auth_create_get_contract_and_health(tmp_path, monkeypatch):
    monkeypatch.setenv("THEME_COMPARE_BUILD_ID", "deployed-main-commit")
    c = client(tmp_path)
    health = c.get("/health")
    assert health.status_code == 200
    assert health.json()["verification_profile"] == "stage6-e2e"
    assert health.json()["build_id"] == "deployed-main-commit"
    assert c.post("/v1/sessions", json=upstream()).status_code == 401
    made = c.post("/v1/sessions", headers={"Authorization": "Bearer secret"}, json=upstream())
    assert made.status_code == 201
    sid = made.json()["session_id"]
    assert (
        c.get(f"/v1/sessions/{sid}", headers={"Authorization": "Bearer secret"}).status_code == 200
    )
    assert (
        c.get(
            f"/v1/sessions/{sid}/next-contract", headers={"Authorization": "Bearer secret"}
        ).json()["phase"]
        == 1
    )


def test_missing_key_fails_closed_and_unhealthy_is_503(tmp_path):
    assert (
        TestClient(create_app(JsonVolumeStorage(tmp_path), None))
        .post("/v1/sessions", json=upstream())
        .status_code
        == 401
    )
    missing = JsonVolumeStorage(tmp_path / "none", create_root=False)
    assert TestClient(create_app(missing, "x")).get("/health").status_code == 503


@pytest.mark.parametrize("raw", [b"{", b'{"x":1,"x":2}', b'{"x":NaN}', b"[]", b"\xff"])
def test_strict_body_rejections(tmp_path, raw):
    response = client(tmp_path).post(
        "/v1/sessions",
        headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
        content=raw,
    )
    assert response.status_code == 422 and response.json()["error"]["state_unchanged"] is True


def test_unknown_property_is_retryable(tmp_path):
    body = upstream()
    body["unknown"] = True
    response = client(tmp_path).post(
        "/v1/sessions", headers={"Authorization": "Bearer secret"}, json=body
    )
    error = response.json()["error"]
    assert response.status_code == 422 and error["retryable"] and not error["terminal"]


def test_corruption_is_terminal(tmp_path):
    c = client(tmp_path)
    headers = {"Authorization": "Bearer secret"}
    sid = c.post("/v1/sessions", headers=headers, json=upstream()).json()["session_id"]
    (tmp_path / f"{sid}.json").write_text("{broken")
    error = c.get(f"/v1/sessions/{sid}", headers=headers)
    assert error.status_code == 500 and error.json()["error"]["terminal"] is True


def test_full_initial_update_api_e2e(tmp_path):
    from phase_fixtures import CANDIDATE, CANDIDATE_B, artifact

    c = client(tmp_path)
    headers = {"Authorization": "Bearer secret"}
    sid = c.post("/v1/sessions", headers=headers, json=upstream()).json()["session_id"]
    for phase in range(1, 11):
        response = c.post(
            f"/v1/sessions/{sid}/phases", headers=headers, json=runtime_artifact(phase)
        )
        assert response.status_code == 200, response.json()
    assert (
        c.get(f"/v1/sessions/{sid}/handoff", headers=headers).json()["active_handoff"]["handoff_id"]
        == "h1"
    )
    update = {
        "new_comparison_as_of": "2025-02-01T00:00:00Z",
        "new_source_cutoff_at": "2025-01-31T00:00:00Z",
        "candidate_inputs": [CANDIDATE, CANDIDATE_B],
    }
    update_response = c.post(f"/v1/sessions/{sid}/updates", headers=headers, json=update)
    assert update_response.status_code == 200, update_response.json()
    for phase in (1, 2):
        response = c.post(
            f"/v1/sessions/{sid}/phases",
            headers=headers,
            json=artifact(phase, "g2", "update", "2025-01-31T00:00:00Z"),
        )
        assert response.status_code == 200, response.json()
    active = c.get(f"/v1/sessions/{sid}/handoff", headers=headers).json()
    assert active["active_handoff"]["handoff_id"] == "h2"
    history = c.get(f"/v1/sessions/{sid}/handoff?include_history=true", headers=headers).json()
    assert [item["handoff_id"] for item in history["handoff_history"]] == ["h1", "h2"]
    restarted = client(tmp_path)
    resumed = restarted.get(f"/v1/sessions/{sid}", headers=headers)
    assert resumed.status_code == 200, resumed.json()
    assert resumed.json()["active_generation_id"] == "g2"
