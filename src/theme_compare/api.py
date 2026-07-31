"""Authenticated FastAPI connection layer for Custom GPT Actions."""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .models import SemanticError, strict_json_loads
from .runtime import RuntimeService
from .storage import JsonVolumeStorage


def create_app(storage: JsonVolumeStorage | None = None, api_key: str | None = None) -> FastAPI:
    volume = storage or JsonVolumeStorage(
        Path(os.environ.get("THEME_COMPARE_STORAGE_ROOT", "/data/sessions"))
    )
    expected_key = api_key if api_key is not None else os.environ.get("THEME_COMPARE_API_KEY", "")
    service = RuntimeService(volume)
    app = FastAPI(
        title="Theme Candidate Comparison Private Runtime",
        version="1.1.0",
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
        return value

    @app.exception_handler(SemanticError)
    async def semantic_error(_request: Request, exc: SemanticError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "accepted": False,
                "error": {"code": "validation_failed", "retryable": True, "message": str(exc)},
            },
        )

    @app.exception_handler(FileNotFoundError)
    async def missing(_request: Request, _exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "session_not_found",
                    "retryable": False,
                    "message": "session not found",
                }
            },
        )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"service": "ok", "storage": volume.health()}

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
        return service.contract(session_id)

    @app.post(
        "/v1/sessions/{session_id}/phases",
        dependencies=[Depends(authorize)],
        operation_id="submitComparisonPhase",
    )
    async def submit(session_id: str, request: Request) -> dict[str, Any]:
        return service.submit(session_id, await body(request))

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

    return app


app = create_app()
