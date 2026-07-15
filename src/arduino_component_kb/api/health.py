"""Liveness and PostgreSQL readiness endpoints."""

from __future__ import annotations

import logging
from typing import Literal, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from arduino_component_kb.config import Settings
from arduino_component_kb.db import DatabaseGateway

router = APIRouter(tags=["health"])
logger = logging.getLogger("arduino_component_kb.health")


class LivenessResponse(BaseModel):
    """Process-level health contract."""

    status: Literal["ok"] = "ok"
    service: str
    version: str


class ReadinessCheck(BaseModel):
    """One dependency readiness result."""

    status: Literal["ready", "not_ready"]


class ReadinessResponse(BaseModel):
    """Aggregate readiness response."""

    status: Literal["ready", "not_ready"]
    checks: dict[str, ReadinessCheck]


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _database(request: Request) -> DatabaseGateway:
    return cast(DatabaseGateway, request.app.state.database)


@router.get("/health", response_model=LivenessResponse)
async def liveness(request: Request) -> LivenessResponse:
    """Report that the HTTP process can serve requests without touching dependencies."""
    settings = _settings(request)
    return LivenessResponse(service=settings.app_name, version=settings.app_version)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(request: Request) -> ReadinessResponse | JSONResponse:
    """Report whether PostgreSQL can execute a bounded probe."""
    try:
        await _database(request).ping()
    except Exception as error:
        logger.error(
            "database_readiness_failed",
            extra={"error_type": type(error).__name__},
        )
        payload = ReadinessResponse(
            status="not_ready",
            checks={"database": ReadinessCheck(status="not_ready")},
        )
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))
    return ReadinessResponse(
        status="ready",
        checks={"database": ReadinessCheck(status="ready")},
    )
