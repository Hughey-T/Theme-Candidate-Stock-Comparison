from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from theme_compare.api import create_app
from theme_compare.storage import JsonVolumeStorage
from tools.generate_action_openapi import build_document, validate_server_url

EXPECTED_OPERATION_IDS = {
    "getRuntimeHealth",
    "createBlindComparisonSessionV2",
    "getBlindPhaseContractV2",
    "submitBlindPhaseV2",
    "startBlindComparisonUpdateV2",
    "discloseMechanicalReconciliationV2",
    "getBlindIndividualHandoffV2",
    "acknowledgeBlindAnalysisV2",
    "getReconciliationHandoffV2",
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
TEST_ORIGIN = "https://theme-compare.example.co.jp"


def document():
    return build_document(TEST_ORIGIN)


def operations(doc):
    for path, item in doc["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


def resolve(doc, schema):
    if "$ref" not in schema:
        return schema
    name = schema["$ref"].rsplit("/", 1)[1]
    return doc["components"]["schemas"][name]


def test_v2_only_openapi_has_exact_unique_operations():
    doc = document()
    assert doc["openapi"] == "3.1.0"
    ids = [operation["operationId"] for _, _, operation in operations(doc)]
    assert set(ids) == EXPECTED_OPERATION_IDS
    assert len(ids) == len(set(ids)) == len(EXPECTED_OPERATION_IDS)
    assert all(not path.startswith("/v1/") for path in doc["paths"])


def test_v2_post_request_bodies_resolve_to_objects():
    doc = document()
    expected = {
        "/v2/sessions": "CreateBlindComparisonSessionV2Request",
        "/v2/sessions/{session_id}/phases": "BlindPhaseArtifactV2",
        "/v2/sessions/{session_id}/updates": "StartBlindComparisonUpdateV2Request",
    }
    for path, name in expected.items():
        operation = doc["paths"][path]["post"]
        assert operation["requestBody"]["required"] is True
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        assert schema == {"$ref": f"#/components/schemas/{name}"}
        assert resolve(doc, schema)["type"] == "object"


def test_v2_mutating_operations_require_idempotency_key():
    doc = document()
    for path in (
        "/v2/sessions",
        "/v2/sessions/{session_id}/phases",
        "/v2/sessions/{session_id}/updates",
    ):
        parameters = doc["paths"][path]["post"].get("parameters", [])
        matches = [p for p in parameters if (p.get("name"), p.get("in")) == ("Idempotency-Key", "header")]
        assert len(matches) == 1
        assert matches[0]["required"] is True


def test_all_component_schemas_are_valid_draft_202012():
    doc = document()
    for schema in doc["components"]["schemas"].values():
        Draft202012Validator.check_schema(schema)


def test_action_routes_exist_in_fastapi(tmp_path):
    doc = document()
    app = create_app(JsonVolumeStorage(tmp_path), "secret")
    actual = {
        (route.path, method.lower())
        for route in app.routes
        if getattr(route, "methods", None)
        for method in route.methods
    }
    declared = {(path, method) for path, method, _ in operations(doc)}
    assert declared <= actual


def test_action_document_is_deterministic():
    first = json.dumps(document(), sort_keys=True, separators=(",", ":"))
    second = json.dumps(document(), sort_keys=True, separators=(",", ":"))
    assert first == second


@pytest.mark.parametrize(
    "url",
    [
        "http://theme.example.co.jp",
        "https://foo.trycloudflare.com",
        "https://runtime.example.com",
        "https://theme.invalid",
        "relative-host",
    ],
)
def test_production_server_url_rejects_ephemeral_or_placeholder_hosts(url):
    with pytest.raises(ValueError):
        validate_server_url(url)
