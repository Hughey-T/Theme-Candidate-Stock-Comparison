from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from theme_compare.api import create_app
from theme_compare.storage import JsonVolumeStorage

OPENAPI_PATH = Path("openapi/custom-gpt-action.openapi.yaml")
DOC = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
EXPECTED_OPERATION_IDS = {
    "getRuntimeHealth",
    "createComparisonSession",
    "getComparisonSession",
    "getNextPhaseContract",
    "submitComparisonPhase",
    "startComparisonUpdate",
    "getActiveComparisonHandoff",
    "createBlindComparisonSessionV2",
    "getBlindPhaseContractV2",
    "submitBlindPhaseV2",
    "startBlindComparisonUpdateV2",
    "discloseMechanicalReconciliationV2",
    "getBlindIndividualHandoffV2",
    "acknowledgeBlindAnalysisV2",
    "getReconciliationHandoffV2",
}
SESSION_OPERATIONS = {
    ("/v1/sessions/{session_id}", "get"),
    ("/v1/sessions/{session_id}/next-contract", "get"),
    ("/v1/sessions/{session_id}/phases", "post"),
    ("/v1/sessions/{session_id}/updates", "post"),
    ("/v1/sessions/{session_id}/handoff", "get"),
}


def operations():
    for path, item in DOC["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


def resolve(schema):
    if "$ref" not in schema:
        return schema
    return DOC["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]


def test_openapi_31_unique_operations_and_no_placeholder():
    assert DOC["openapi"] == "3.1.0"
    ids = [operation["operationId"] for _, _, operation in operations()]
    assert set(ids) == EXPECTED_OPERATION_IDS
    assert len(ids) == len(set(ids)) == len(EXPECTED_OPERATION_IDS)
    assert all("YOUR_" not in server["url"] for server in DOC["servers"])


def test_route_method_and_auth_alignment(tmp_path):
    app = create_app(JsonVolumeStorage(tmp_path), "x")
    actual = {
        (route.path, next(iter(route.methods)).lower())
        for route in app.routes
        if getattr(route, "methods", None)
    }
    declared = {(path, method) for path, method, _ in operations()}
    assert declared <= actual
    for path, _, operation in operations():
        assert operation.get("security", DOC.get("security")) == (
            [] if path == "/health" else [{"BearerAuth": []}]
        )


def test_named_request_response_contracts_are_closed():
    required = {
        "CreateSessionRequest",
        "CreateSessionResponse",
        "SessionSummary",
        "NextPhaseContract",
        "PhaseArtifact",
        "PhaseAcceptedResponse",
        "StartUpdateRequest",
        "StartUpdateResponse",
        "ActiveHandoffResponse",
        "ValidationError",
        "TerminalIntegrityError",
        "HealthResponse",
    }
    assert required <= DOC["components"]["schemas"].keys()
    for name in required:
        schema = DOC["components"]["schemas"][name]
        if schema.get("type") == "object" and "oneOf" not in schema:
            assert schema.get("additionalProperties") is False
            assert schema.get("required")
        Draft202012Validator.check_schema(schema)


def test_create_request_is_packaged_upstream_contract():
    packaged = json.loads(
        Path("src/theme_compare/schemas/upstream-theme-handoff.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert DOC["components"]["schemas"]["CreateSessionRequest"] == packaged


def test_phase_artifact_is_packaged_object_contract():
    packaged = json.loads(
        Path("src/theme_compare/schemas/phase-artifact.schema.json").read_text(encoding="utf-8")
    )
    schema = DOC["components"]["schemas"]["PhaseArtifact"]
    assert schema == packaged
    assert schema["type"] == "object"
    assert len(schema["oneOf"]) == 12


def test_path_item_parameters_are_not_used():
    for path_item in DOC["paths"].values():
        assert "parameters" not in path_item


def test_session_id_is_required_at_operation_level():
    for path, method in SESSION_OPERATIONS:
        parameters = DOC["paths"][path][method].get("parameters", [])
        matches = [
            parameter
            for parameter in parameters
            if (parameter.get("name"), parameter.get("in")) == ("session_id", "path")
        ]
        assert len(matches) == 1
        assert matches[0]["required"] is True
        assert parameters[0] == matches[0]


def test_handoff_keeps_session_id_and_include_history():
    parameters = DOC["paths"]["/v1/sessions/{session_id}/handoff"]["get"]["parameters"]
    assert [(parameter["name"], parameter["in"]) for parameter in parameters] == [
        ("session_id", "path"),
        ("include_history", "query"),
    ]


def test_submit_phase_request_resolves_to_object_schema():
    schema = DOC["paths"]["/v1/sessions/{session_id}/phases"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    resolved = resolve(schema)
    assert resolved["type"] == "object"
    assert len(resolved["oneOf"]) == 12


def test_openapi_generation_is_byte_stable():
    before = OPENAPI_PATH.read_bytes()
    subprocess.run(
        [sys.executable, "tools/generate_openapi.py"],
        check=True,
    )
    assert OPENAPI_PATH.read_bytes() == before
