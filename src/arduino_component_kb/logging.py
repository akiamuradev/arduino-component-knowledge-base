"""Privacy-aware JSON logging and request correlation."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from time import perf_counter
from typing import Final
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from arduino_component_kb.config import LogLevel
from arduino_component_kb.security import SECURITY_HEADERS

REQUEST_ID_HEADER: Final = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    """Return the current request ID outside the HTTP layer."""
    return _request_id.get()


def normalize_request_id(candidate: str | None) -> str:
    """Accept a bounded safe identifier or generate a UUID."""
    if candidate is not None and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return str(uuid4())


class JsonFormatter(logging.Formatter):
    """Render bounded structured fields and avoid arbitrary record extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or current_request_id()
        if request_id:
            payload["request_id"] = request_id
        for key in (
            "method",
            "route",
            "status_code",
            "duration_ms",
            "error_type",
            "source",
            "revision",
            "kicad_revision",
            "kicad_index_sha256",
            "adapter_version",
            "files_scanned",
            "entries_discovered",
            "entries_parsed",
            "warnings_count",
            "failed_count",
            "bytes_downloaded",
            "import_run_id",
            "import_stage",
            "attempt",
            "outcome",
            "failure_code",
            "shadow_mode",
            "quality_score",
            "comparison_conflicts",
            "field_coverage_basis_points",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: LogLevel) -> None:
    """Configure the application logger idempotently."""
    logger = logging.getLogger("arduino_component_kb")
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a validated request ID and emit one completion event."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
        token: Token[str | None] = _request_id.set(request_id)
        started = perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            for name, value in SECURITY_HEADERS.items():
                response.headers[name] = value
            return response
        except Exception as error:
            logging.getLogger("arduino_component_kb.http").error(
                "unhandled_application_error",
                extra={"request_id": request_id, "error_type": type(error).__name__},
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "Unexpected server error.",
                        "request_id": request_id,
                    }
                },
                headers={REQUEST_ID_HEADER: request_id, **SECURITY_HEADERS},
            )
            return response
        finally:
            route_object = request.scope.get("route")
            route = getattr(route_object, "path", "unmatched")
            status_code = response.status_code if response is not None else 500
            logging.getLogger("arduino_component_kb.http").info(
                "http_request_completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                },
            )
            _request_id.reset(token)
