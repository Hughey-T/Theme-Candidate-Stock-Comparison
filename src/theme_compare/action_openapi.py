"""Canonical v2-only Custom GPT Action OpenAPI generation."""

from __future__ import annotations

import argparse
import json
from importlib import resources
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_OUTPUT = Path("openapi/custom-gpt-action.v2.openapi.json")

_PHASE_DEF_COMPONENT_NAMES = {
    "horizon": "BlindPhaseHorizon",
    "information": "BlindPhaseInformation",
    "judgment": "BlindPhaseJudgment",
    "ranking": "BlindPhaseRanking",
    "candidateSetTransition": "BlindPhaseCandidateSetTransition",
    "pairwise": "BlindPhasePairwise",
    "sensitivity": "BlindPhaseSensitivity",
}


def load_schema(name: str) -> dict[str, object]:
    raw = resources.files("theme_compare.schemas").joinpath(name).read_text(encoding="utf-8")
    value: dict[str, object] = json.loads(raw)
    value.pop("$schema", None)
    value.pop("$id", None)
    return value


def normalize_action_schema(
    value: object,
    *,
    def_component_names: dict[str, str] | None = None,
) -> object:
    """Normalize JSON Schema features that the Custom GPT Action editor handles narrowly.

    The runtime keeps validating against the canonical Draft 2020-12 schema. This
    normalization only affects the OpenAPI document supplied to ChatGPT Actions.
    """
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            if key == "$defs":
                continue
            if (
                key == "$ref"
                and isinstance(item, str)
                and item.startswith("#/$defs/")
                and def_component_names is not None
            ):
                def_name = item.removeprefix("#/$defs/")
                component_name = def_component_names.get(def_name)
                if component_name is None:
                    raise ValueError(f"unmapped local schema definition: {def_name}")
                result[key] = f"#/components/schemas/{component_name}"
            else:
                result[key] = normalize_action_schema(
                    item,
                    def_component_names=def_component_names,
                )

        if result.get("type") == "object" and "properties" not in result:
            result["properties"] = {}

        enum_values = result.get("enum")
        if "type" not in result and isinstance(enum_values, list) and enum_values:
            if all(isinstance(item, str) for item in enum_values):
                result["type"] = "string"

        return result

    if isinstance(value, list):
        return [
            normalize_action_schema(item, def_component_names=def_component_names) for item in value
        ]
    return value


def phase_artifact_components() -> tuple[dict[str, object], dict[str, object]]:
    raw = load_schema("comparison-contract-v2.schema.json")
    raw_defs = raw.pop("$defs", {})
    if not isinstance(raw_defs, dict):
        raise ValueError("comparison contract $defs must be an object")

    components: dict[str, object] = {}
    for def_name, component_name in _PHASE_DEF_COMPONENT_NAMES.items():
        definition = raw_defs.get(def_name)
        if not isinstance(definition, dict):
            raise ValueError(f"comparison contract definition is missing: {def_name}")
        normalized = normalize_action_schema(
            definition,
            def_component_names=_PHASE_DEF_COMPONENT_NAMES,
        )
        if not isinstance(normalized, dict):
            raise TypeError(f"normalized component must be an object: {component_name}")
        components[component_name] = normalized

    phase_artifact = normalize_action_schema(
        raw,
        def_component_names=_PHASE_DEF_COMPONENT_NAMES,
    )
    if not isinstance(phase_artifact, dict):
        raise TypeError("normalized phase artifact must be an object")
    return phase_artifact, components


def validate_server_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise ValueError("server URL must be an absolute https URL")
    forbidden = (
        "trycloudflare.com",
        "example.com",
        "example.org",
        "example.net",
        ".invalid",
    )
    if host.endswith(forbidden):
        raise ValueError("production Action URL must be a stable non-placeholder hostname")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("server URL must be an HTTPS origin without path/query/fragment")
    return value.rstrip("/")


def response(description: str, schema_name: str = "GenericResponse") -> dict[str, object]:
    return {
        "description": description,
        "content": {
            "application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}
        },
    }


def standard_responses(
    success: str = "200",
    success_schema: str = "GenericResponse",
) -> dict[str, object]:
    return {
        success: response("Success", success_schema),
        "401": response("Authentication failure"),
        "404": response("Session not found"),
        "422": response("Validation or transition failure"),
        "500": response("Storage or persisted-integrity failure"),
        "503": response("Runtime unavailable"),
    }


def session_parameter() -> dict[str, object]:
    return {
        "name": "session_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string", "pattern": "^s_[0-9a-f]{32}$"},
    }


def idempotency_parameter() -> dict[str, object]:
    return {
        "name": "idempotency_key",
        "in": "query",
        "required": True,
        "description": (
            "Stable unique token for safe retry of this logical POST operation. "
            "Reuse it only when retrying the exact same logical request."
        ),
        "schema": {"type": "string", "minLength": 8, "maxLength": 200},
    }


def request_body(schema_name: str) -> dict[str, object]:
    return {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}
        },
    }


def _horizon_schema() -> dict[str, object]:
    return {
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


def _create_request_schema() -> dict[str, object]:
    return {
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


def _create_response_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "accepted",
            "session_id",
            "generation_id",
            "next_phase",
            "candidate_order",
            "contract_version",
        ],
        "properties": {
            "accepted": {"type": "boolean"},
            "session_id": {"type": "string", "pattern": "^s_[0-9a-f]{32}$"},
            "generation_id": {"type": "string"},
            "next_phase": {"type": "integer"},
            "candidate_order": {
                "type": "array",
                "items": {"type": "string"},
            },
            "contract_version": {"type": "string", "const": "2.0.0"},
        },
    }


def _update_request_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "new_generation_id",
            "analysis_as_of",
            "source_cutoff_at",
            "candidates",
        ],
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


def _generic_response_schema() -> dict[str, object]:
    return {
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
            "verification_profile": {"type": "string"},
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


def _paths() -> dict[str, object]:
    session = session_parameter
    idem = idempotency_parameter
    create_responses = standard_responses(success_schema="CreateBlindComparisonSessionV2Response")
    return {
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
                "parameters": [idem()],
                "requestBody": request_body("CreateBlindComparisonSessionV2Request"),
                "responses": create_responses,
            }
        },
        "/v2/session-create-result": {
            "get": {
                "operationId": "recoverBlindComparisonSessionV2",
                "summary": "Recover a completed create-session result by idempotency key",
                "parameters": [idem()],
                "responses": create_responses,
            }
        },
        "/v2/sessions/{session_id}/next-contract": {
            "get": {
                "operationId": "getBlindPhaseContractV2",
                "summary": "Get the exact current phase contract",
                "parameters": [session()],
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/phases": {
            "post": {
                "operationId": "submitBlindPhaseV2",
                "summary": "Submit exactly one current phase artifact",
                "parameters": [session(), idem()],
                "requestBody": request_body("BlindPhaseArtifactV2"),
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/updates": {
            "post": {
                "operationId": "startBlindComparisonUpdateV2",
                "summary": "Start a strictly newer update generation",
                "parameters": [session(), idem()],
                "requestBody": request_body("StartBlindComparisonUpdateV2Request"),
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/reconciliation": {
            "get": {
                "operationId": "discloseMechanicalReconciliationV2",
                "summary": "Disclose reconciliation after independent AI freeze",
                "parameters": [session()],
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/handoffs/blind": {
            "get": {
                "operationId": "getBlindIndividualHandoffV2",
                "summary": "Get non-persuasive blind individual-analysis handoff",
                "parameters": [session()],
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/handoffs/blind/acknowledge": {
            "post": {
                "operationId": "acknowledgeBlindAnalysisV2",
                "summary": "Acknowledge completed independent blind analysis",
                "parameters": [session()],
                "responses": standard_responses(),
            }
        },
        "/v2/sessions/{session_id}/handoffs/reconciliation": {
            "get": {
                "operationId": "getReconciliationHandoffV2",
                "summary": "Get reconciliation handoff after acknowledgement",
                "parameters": [session()],
                "responses": standard_responses(),
            }
        },
    }


def build_document(server_url: str) -> dict[str, object]:
    phase_artifact, phase_components = phase_artifact_components()
    schemas: dict[str, object] = {
        "CandidateIdentity": normalize_action_schema(
            load_schema("normalized-candidate.schema.json")
        ),
        "Horizon": _horizon_schema(),
        "FlexibleHandoff": {
            "type": "object",
            "additionalProperties": True,
            "properties": {},
        },
        "CreateBlindComparisonSessionV2Request": _create_request_schema(),
        "CreateBlindComparisonSessionV2Response": _create_response_schema(),
        "BlindPhaseArtifactV2": phase_artifact,
        **phase_components,
        "StartBlindComparisonUpdateV2Request": _update_request_schema(),
        "GenericResponse": _generic_response_schema(),
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Theme Candidate Stock Comparison V2",
            "version": "2.0.0",
            "description": (
                "Canonical v2-only Custom GPT Action contract. Legacy v1 is intentionally excluded."
            ),
        },
        "servers": [{"url": server_url}],
        "security": [{"BearerAuth": []}],
        "paths": _paths(),
        "components": {
            "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": schemas,
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
