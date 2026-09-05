"""Authenticated, factory-created FastAPI connection layer for Custom GPT Actions."""

from __future__ import annotations

import hashlib
import hmac
import os
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .idempotency import IdempotencyStore
from .models import SemanticError, strict_json_loads
from .phase2_contract import enrich_phase2_contract, rewrite_phase2_validation_error
from .runtime import RuntimeIntegrityError, RuntimeService
from .storage import JsonVolumeStorage, StorageError
from .v2_runtime import V2RuntimeService

CONTRACT_VERSION = "2.0.0"
API_PROFILE = "custom-gpt-v2"
VERIFICATION_PROFILE = "stage6-e2e"


def _schema_fingerprint() -> str:
    raw = (
        resources.files("theme_compare.schemas")
        .joinpath("comparison-contract-v2.schema.json")
        .read_bytes()
    )
    return hashlib.sha256(raw).hexdigest()


def app_factory() -> FastAPI:
    """Uvicorn factory; importing this module has no filesystem side effect."""
    root = os.environ.get("THEME_COMPARE_STORAGE_ROOT")
    if not root:
        root = str(Path.home() / ".theme-compare" / "sessions")
    return create_app(JsonVolumeStorage(Path(root)), os.environ.get("THEME_COMPARE_API_KEY"))


def create_app(storage: JsonVolumeStorage, api_key: str | None) -> FastAPI:
    service = RuntimeService(storage)
    v2 = V2RuntimeService(storage)
    idempotency = IdempotencyStore(storage.root)
    expected_key = api_key or ""
    build_id = os.environ.get("THEME_COMPARE_BUILD_ID", "development")
    schema_sha256 = _schema_fingerprint()
    app = FastAPI(
        title="Theme Candidate Comparison Private Runtime",
        version=CONTRACT_VERSION,
        docs_url=None,
        redoc_url=None,
    )

    def authorize(request: Request) -> None:
        supplied = request.headers.get("authorization", "")
        valid = (
            bool(expected_key)
            and supplied.startswith("Bearer ")
            and hmac.compare_digest(supplied[7:].encode(), expected_key.encode())
        )
        if not valid:
            raise HTTPException(
                status_code=401,
                detail={"code": "unauthorized", "message": "valid Bearer API key required"},
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def body(request: Request) -> dict[str, Any]:
        value = strict_json_loads(await request.body())
        if not isinstance(value, dict):
            raise SemanticError("request body must be a JSON object")
        request.state.generation_id = value.get("generation_id") or value.get("new_generation_id")
        request.state.phase = value.get("phase")
        return value

    def resolve_idempotency_key(query_key: str | None, header_key: str | None) -> str:
        if query_key and header_key and query_key != header_key:
            raise SemanticError("conflicting idempotency keys")
        key = query_key or header_key
        if not key:
            raise SemanticError("idempotency key is required")
        if not 8 <= len(key) <= 200:
            raise SemanticError("idempotency key must be between 8 and 200 characters")
        return key

    def error_content(
        request: Request,
        exc: Exception,
        *,
        terminal: bool,
        category: str,
    ) -> dict[str, Any]:
        session_id = request.path_params.get("session_id")
        stage = "persisted_state" if terminal else "request_or_transition"
        return {
            "accepted": False,
            "error": {
                "code": "integrity_failure" if terminal else "validation_failed",
                "category": category,
                "retryable": not terminal,
                "terminal": terminal,
                "stage": stage,
                "message": str(exc),
                "session_id": session_id,
                "generation_id": getattr(request.state, "generation_id", None),
                "phase": getattr(request.state, "phase", None),
                "state_unchanged": True,
            },
        }

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code == 401:
            return JSONResponse(
                status_code=401,
                headers=exc.headers,
                content={
                    "accepted": False,
                    "error": {
                        "code": "unauthorized",
                        "category": "auth",
                        "retryable": False,
                        "terminal": False,
                        "message": "valid Bearer API key required",
                        "state_unchanged": True,
                    },
                },
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(SemanticError)
    async def semantic_error(request: Request, exc: SemanticError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_content(request, exc, terminal=False, category="validation_transition"),
        )

    @app.exception_handler(RuntimeIntegrityError)
    async def runtime_integrity_error(request: Request, exc: RuntimeIntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_content(request, exc, terminal=True, category="integrity"),
        )

    @app.exception_handler(StorageError)
    async def storage_error(request: Request, exc: StorageError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_content(request, exc, terminal=True, category="storage_integrity"),
        )

    @app.exception_handler(FileNotFoundError)
    async def missing(request: Request, _exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "accepted": False,
                "error": {
                    "code": "session_not_found",
                    "category": "validation_transition",
                    "retryable": False,
                    "terminal": False,
                    "stage": "load",
                    "message": "session not found",
                    "session_id": request.path_params.get("session_id"),
                    "generation_id": None,
                    "phase": None,
                    "state_unchanged": True,
                },
            },
        )

    @app.get("/health", operation_id="getRuntimeHealth")
    def health() -> JSONResponse:
        healthy = storage.health()
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={
                "service": "ok" if healthy else "unhealthy",
                "storage": "ok" if healthy else "unhealthy",
                "ready": healthy,
                "contract_version": CONTRACT_VERSION,
                "api_profile": API_PROFILE,
                "verification_profile": VERIFICATION_PROFILE,
                "build_id": build_id,
                "schema_sha256": schema_sha256,
            },
        )

    @app.post(
        "/v1/sessions",
        dependencies=[Depends(authorize)],
        operation_id="createComparisonSession",
        status_code=201,
    )
    async def create(request: Request) -> dict[str, Any]:
        return service.create(await body(request))

    @app.get(
        "/v1/sessions/{session_id}",
        dependencies=[Depends(authorize)],
        operation_id="getComparisonSession",
    )
    def get(session_id: str) -> dict[str, Any]:
        return service.summary(session_id)

    @app.get(
        "/v1/sessions/{session_id}/next-contract",
        dependencies=[Depends(authorize)],
        operation_id="getNextPhaseContract",
    )
    def contract(session_id: str) -> dict[str, Any]:
        return enrich_phase2_contract(service.contract(session_id))

    @app.post(
        "/v1/sessions/{session_id}/phases",
        dependencies=[Depends(authorize)],
        operation_id="submitComparisonPhase",
    )
    async def submit(session_id: str, request: Request) -> dict[str, Any]:
        artifact = await body(request)
        try:
            return service.submit(session_id, artifact)
        except SemanticError as exc:
            raise rewrite_phase2_validation_error(exc, artifact) from exc

    @app.post(
        "/v1/sessions/{session_id}/updates",
        dependencies=[Depends(authorize)],
        operation_id="startComparisonUpdate",
    )
    async def update(session_id: str, request: Request) -> dict[str, Any]:
        return service.update(session_id, await body(request))

    @app.get(
        "/v1/sessions/{session_id}/handoff",
        dependencies=[Depends(authorize)],
        operation_id="getActiveComparisonHandoff",
    )
    def handoff(session_id: str, include_history: bool = Query(False)) -> dict[str, Any]:
        return service.handoff(session_id, include_history)

    @app.post(
        "/v2/sessions",
        dependencies=[Depends(authorize)],
        operation_id="createBlindComparisonSessionV2",
    )
    async def create_v2(
        request: Request,
        idempotency_key: str | None = Query(None),
        idempotency_header: str | None = Header(None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        payload = await body(request)
        key = resolve_idempotency_key(idempotency_key, idempotency_header)
        return idempotency.execute("v2:create", key, payload, lambda: v2.create(payload))

    @app.get(
        "/v2/session-create-result",
        dependencies=[Depends(authorize)],
        operation_id="recoverBlindComparisonSessionV2",
    )
    def recover_create_v2(idempotency_key: str = Query(...)) -> dict[str, Any]:
        result = idempotency.read_result("v2:create", idempotency_key)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "idempotency_result_not_found",
                    "message": "no completed session-create result exists for this idempotency key",
                },
            )
        return result

    @app.get(
        "/v2/sessions/{session_id}/next-contract",
        dependencies=[Depends(authorize)],
        operation_id="getBlindPhaseContractV2",
    )
    def contract_v2(session_id: str) -> dict[str, Any]:
        return v2.contract(session_id)

    @app.post(
        "/v2/sessions/{session_id}/phases",
        dependencies=[Depends(authorize)],
        operation_id="submitBlindPhaseV2",
    )
    async def submit_v2(
        session_id: str,
        request: Request,
        idempotency_key: str | None = Query(None),
        idempotency_header: str | None = Header(None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        payload = await body(request)
        key = resolve_idempotency_key(idempotency_key, idempotency_header)
        scope = f"v2:submit:{session_id}:{payload.get('generation_id')}:{payload.get('phase')}"
        return idempotency.execute(scope, key, payload, lambda: v2.submit(session_id, payload))

    @app.post(
        "/v2/sessions/{session_id}/updates",
        dependencies=[Depends(authorize)],
        operation_id="startBlindComparisonUpdateV2",
    )
    async def update_v2(
        session_id: str,
        request: Request,
        idempotency_key: str | None = Query(None),
        idempotency_header: str | None = Header(None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        payload = await body(request)
        key = resolve_idempotency_key(idempotency_key, idempotency_header)
        return idempotency.execute(
            f"v2:update:{session_id}",
            key,
            payload,
            lambda: v2.start_update(session_id, payload),
        )

    @app.get(
        "/v2/sessions/{session_id}/reconciliation",
        dependencies=[Depends(authorize)],
        operation_id="discloseMechanicalReconciliationV2",
    )
    def reconcile_v2(session_id: str) -> dict[str, Any]:
        return v2.disclose(session_id)

    @app.get(
        "/v2/sessions/{session_id}/handoffs/blind",
        dependencies=[Depends(authorize)],
        operation_id="getBlindIndividualHandoffV2",
    )
    def blind_handoff_v2(session_id: str) -> dict[str, Any]:
        return v2.handoff(session_id, False)

    @app.post(
        "/v2/sessions/{session_id}/handoffs/blind/acknowledge",
        dependencies=[Depends(authorize)],
        operation_id="acknowledgeBlindAnalysisV2",
    )
    def acknowledge_blind_v2(session_id: str) -> dict[str, Any]:
        return v2.acknowledge_blind(session_id)

    @app.get(
        "/v2/sessions/{session_id}/handoffs/reconciliation",
        dependencies=[Depends(authorize)],
        operation_id="getReconciliationHandoffV2",
    )
    def reconciliation_handoff_v2(session_id: str) -> dict[str, Any]:
        return v2.handoff(session_id, True)

    return app
