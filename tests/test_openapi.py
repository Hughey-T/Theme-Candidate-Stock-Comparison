from __future__ import annotations
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from theme_compare.api import create_app
from theme_compare.storage import JsonVolumeStorage

DOC = json.loads(Path("openapi/custom-gpt-action.openapi.yaml").read_text())


def operations():
    for path, item in DOC["paths"].items():
        for method, operation in item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                yield path, method, operation


def resolve(ref):
    return DOC["components"]["schemas"][ref.rsplit("/", 1)[1]]


def test_openapi_31_unique_operations_and_no_placeholder():
    assert DOC["openapi"] == "3.1.0"
    ids = [op["operationId"] for _, _, op in operations()]
    assert len(ids) == len(set(ids))
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
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False and schema.get("required")
        Draft202012Validator.check_schema(schema)


def test_create_request_is_packaged_upstream_contract():
    packaged = json.loads(
        Path("src/theme_compare/schemas/upstream-theme-handoff.schema.json").read_text()
    )
    assert DOC["components"]["schemas"]["CreateSessionRequest"] == packaged


def test_phase_artifact_is_packaged_contract():
    packaged = json.loads(Path("src/theme_compare/schemas/phase-artifact.schema.json").read_text())
    assert DOC["components"]["schemas"]["PhaseArtifact"] == packaged
