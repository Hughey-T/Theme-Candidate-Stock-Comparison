"""Generate the only supported Custom GPT Action contract (v2-only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parents[1]
SCHEMA_ROOT = ROOT / "src" / "theme_compare" / "schemas"
DEFAULT_OUTPUT = ROOT / "openapi" / "custom-gpt-action.v2.openapi.json"


def load_schema(name: str) -> dict:
    value = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    value.pop("$schema", None)
    value.pop("$id", None)
    return value


def rebase_local_refs(value: object, component_name: str) -> object:
    """Rebase schema-local refs after embedding a schema under OpenAPI components."""
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str) and item.startswith("#/"):
                result[key] = f"#/components/schemas/{component_name}{item[1:]}"
            else:
                result[key] = rebase_local_refs(item, component_name)
        return result
    if isinstance(value, list):
        return [rebase_local_refs(item, component_name) for item in value]
    return value


def validate_server_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise ValueError("server URL must be an absolute https URL")
    forbidden = ("trycloudflare.com", "example.com", "example.org", "example.net", ".invalid")
    if host.endswith(forbidden):
        raise ValueError("production Action URL must be a stable non-placeholder hostname")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("server URL must be an HTTPS origin without path/query/fragment")
    return value.rstrip("/")


def response(description: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/GenericResponse"}}},
    }


def standard_responses(success: str = "200") -> dict:
    return {
        success: response("Success"),
        "401": response("Authentication failure"),
        "404": response("Session not found"),
        "422": response("Validation or transition failure"),
        "500": response("Storage or persisted-integrity failure"),
        "503": response("Runtime unavailable"),
    }


def session_parameter() -> dict:
    return {
        "name": "session_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string", "pattern": "^s_[0-9a-f]{32}$"},
    }


def idempotency_parameter() -> dict:
    return {
        "name": "Idempotency-Key",
        "in": "header",
        "required": True,
        "description": "Stable unique key for safe retry of this logical POST operation.",
        "schema": {"type": "string", "minLength": 8, "maxLength": 200},
    }


def request_body(schema_name: str) -> dict:
    return {
        "required": True,
        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}},
    }


def build_document(server_url: str) -> dict:
    candidate = load_schema("normalized-candidate.schema.json")
    phase_artifact = rebase_local_refs(
        load_schema("comparison-contract-v2.schema.json"), "BlindPhaseArtifactV2"
    )
    horizon = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "horizon_id",
            "minimum_months",
            "maximum_months",
            "benchmark",
            "required_return",
        ],
        "properties": {
            "horizon_id": {"type": "string", "minLength": 1},
            "minimum_months": {"type": "integer", "minimum": 1},
            "maximum_months": {"type": "integer", "minimum": 1},
            "benchmark": {"type": "string", "minLength": 1},
            "required_return": {"type": "number"},
        },
    }
    handoff = {"type": "object", "additionalProperties": True}
    create_request = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "contract_version",
            "mode",
            "theme",
            "analysis_as_of",
            "source_cutoff_at",
            "candidates",
            "horizons",
        ],
        "properties": {
            "contract_version": {"type": "string", "const": "2.0.0"},
            "mode": {"type": "string", "enum": ["standalone", "pipeline"]},
            "theme": {"type": "string", "minLength": 1},
            "analysis_as_of": {"type": "string", "format": "date-time"},
            "source_cutoff_at": {"type": "string", "format": "date-time"},
            "candidates": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "items": {"$ref": "#/components/schemas/CandidateIdentity"},
            },
            "horizons": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/components/schemas/Horizon"},
            },
            "blind_handoff": {"$ref": "#/components/schemas/FlexibleHandoff"},
            "reconciliation_handoff": {"$ref": "#/components/schemas/FlexibleHandoff"},
        },
    }
    update_request = {
        "type": "object",
        "additionalProperties": False,
        "required": ["new_generation_id", "analysis_as_of", "source_cutoff_at", "candidates"],
        "properties": {
            "new_generation_id": {"type": "string", "minLength": 1},
            "analysis_as_of": {"type": "string", "format": "date-time"},
            "source_cutoff_at": {"type": "string", "format": "date-time"},
            "candidates": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "items": {"$ref": "#/components/schemas/CandidateIdentity"},
            },
        },
    }
    generic_response = {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "accepted": {"type": "boolean"},
            "session_id": {"type": "string"},
            "generation_id": {"type": "string"},
            "next_phase": {"type": ["integer", "null"]},
            "completed_phase": {"type": "integer"},
            "phase": {"type": "integer"},
            "status": {"type": "string"},
            "workflow": {"type": "string"},
            "service": {"type": "string"},
            "storage": {"type": "string"},
            "ready": {"type": "boolean"},
            "contract_version": {"type": "string"},
            "api_profile": {"type": "string"},
            "build_id": {"type": "string"},
            "schema_sha256": {"type": "string"},
            "error": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "code": {"type": "string"},
                    "category": {"type": "string"},
                    "message": {"type": "string"},
                    "retryable": {"type": "boolean"},
                    "terminal": {"type": "boolean"},
                },
            },
        },
    }

    paths = {
        "/health": {
            "get": {
                "operationId": "getRuntimeHealth",
                "summary": "Check runtime readiness and contract identity",
                "security": [],
                "responses": {"200": response("Ready"), "503": response("Unavailable")},
            }
        },
        "/v2/sessions": {
            "post": {
                "operationId": "createBlindComparisonSessionV2",
                "summary": "Create a contract 2.0 comparison session",
                "parameters": [idempotency_parameter()],
                "requestBody": request_body("CreateBlindComparisonSessionV2Request"),
                "responses": standard_responses("201"),
            }
        },
        "/v2/sessions/{session_id}/next-contract": {
            "get": {
                "operationId": "getBlindPhaseContractV2",
                "summary": "Get the exact current phase contract",
                "parameters": [session_parameter()],
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/phases": {
            "post": {
                "operationId": "submitBlindPhaseV2",
                "summary": "Submit exactly one current phase artifact",
                "parameters": [session_parameter(), idempotency_parameter()],
                "requestBody": request_body("BlindPhaseArtifactV2"),
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/updates": {
            "post": {
                "operationId": "startBlindComparisonUpdateV2",
                "summary": "Start a strictly newer update generation",
                "parameters": [session_parameter(), idempotency_parameter()],
                "requestBody": request_body("StartBlindComparisonUpdateV2Request"),
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/reconciliation": {
            "get": {
                "operationId": "discloseMechanicalReconciliationV2",
                "summary": "Disclose reconciliation after independent AI freeze",
                "parameters": [session_parameter()],
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/handoffs/blind": {
            "get": {
                "operationId": "getBlindIndividualHandoffV2",
                "summary": "Get non-persuasive blind individual-analysis handoff",
                "parameters": [session_parameter()],
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/handoffs/blind/acknowledge": {
            "post": {
                "operationId": "acknowledgeBlindAnalysisV2",
                "summary": "Acknowledge completed independent blind analysis",
                "parameters": [session_parameter()],
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/handoffs/reconciliation": {
            "get": {
                "operationId": "getReconciliationHandoffV2",
                "summary": "Get reconciliation handoff after acknowledgement",
                "parameters": [session_parameter()],
                "responses": standard_responses(),
            }
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Theme Candidate Stock Comparison V2",
            "version": "2.0.0",
            "description": "Canonical v2-only Custom GPT Action contract. Legacy v1 is intentionally excluded.",
        },
        "servers": [{"url": server_url}],
        "security": [{"BearerAuth": []}],
        "paths": paths,
        "components": {
            "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": {
                "CandidateIdentity": candidate,
                "Horizon": horizon,
                "FlexibleHandoff": handoff,
                "CreateBlindComparisonSessionV2Request": create_request,
                "BlindPhaseArtifactV2": phase_artifact,
                "StartBlindComparisonUpdateV2Request": update_request,
                "GenericResponse": generic_response,
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", required=True, type=validate_server_url)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    document = build_document(args.server_url)
    encoded = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")


if __name__ == "__main__":
    main()
