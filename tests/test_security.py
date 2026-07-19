"""Executable browser-boundary and mutation authorization contracts."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Response
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import csrf_principal
from arduino_component_kb.api.imports import get_import
from arduino_component_kb.api.imports import router as imports_router
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.config import Settings
from arduino_component_kb.imports.models import ImportJob
from arduino_component_kb.main import create_app
from arduino_component_kb.security import CONTENT_SECURITY_POLICY, SECURITY_HEADERS, is_same_origin

ROOT = Path(__file__).resolve().parents[1]


class FakeDatabase:
    async def ping(self) -> None:
        return None

    async def dispose(self) -> None:
        return None


def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
    )


def principal(role: Role, *, user_id: UUID | None = None) -> Principal:
    return Principal(
        user_id=user_id or uuid4(),
        login="user",
        display_name="User",
        roles=frozenset({role}),
        session_id=uuid4(),
        csrf_hash="csrf-hash",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _dependency_calls(dependant: Dependant) -> Iterator[Callable[..., object]]:
    for child in dependant.dependencies:
        if child.call is not None:
            yield child.call
        yield from _dependency_calls(child)


def test_every_authenticated_mutation_requires_csrf() -> None:
    app = create_app(settings(), FakeDatabase())
    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = route.methods or set()
        if not methods.intersection({"POST", "PUT", "PATCH", "DELETE"}):
            continue
        if route.path == "/api/v1/auth/login":
            continue
        if csrf_principal not in set(_dependency_calls(route.dependant)):
            missing.append(f"{','.join(sorted(methods))} {route.path}")
    assert missing == []


def test_sensitive_route_groups_keep_backend_role_dependencies() -> None:
    app = create_app(settings(), FakeDatabase())
    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path.startswith(("/api/v1/admin", "/api/v1/duplicate-candidates")):
            required = frozenset({Role.ADMINISTRATOR})
        elif route.path.startswith(("/api/v1/workspace", "/api/v1/media", "/api/v1/import-jobs")):
            required = frozenset({Role.TEACHER, Role.ADMINISTRATOR})
        else:
            continue
        role_sets = {
            frozenset(roles)
            for call in _dependency_calls(route.dependant)
            if (roles := inspect.getclosurevars(call).nonlocals.get("allowed")) is not None
        }
        if required not in role_sets:
            missing.append(route.path)
    assert missing == []


def test_repository_import_workflow_requires_administrator_role() -> None:
    protected_paths = {
        "/api/v1/import-jobs/repository/discovery",
        "/api/v1/import-jobs/repository/entries",
        "/api/v1/import-jobs/repository/preview",
        "/api/v1/import-jobs/repository",
    }
    checked: set[str] = set()
    for route in imports_router.routes:
        if not isinstance(route, APIRoute) or route.path not in protected_paths:
            continue
        role_sets = {
            frozenset(roles)
            for call in _dependency_calls(route.dependant)
            if (roles := inspect.getclosurevars(call).nonlocals.get("allowed")) is not None
        }
        assert frozenset({Role.ADMINISTRATOR}) in role_sets
        checked.add(route.path)
    assert checked == protected_paths


def test_security_headers_are_present_without_permissive_cors() -> None:
    with TestClient(create_app(settings(), FakeDatabase())) as client:
        response = client.get("/health")
    assert response.status_code == 200
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value
    assert response.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    assert "access-control-allow-origin" not in response.headers


def test_reverse_proxy_and_threat_model_preserve_security_boundary() -> None:
    proxy = (ROOT / "deploy" / "reverse-proxy" / "default.conf").read_text(encoding="utf-8")
    assert CONTENT_SECURITY_POLICY in proxy
    assert proxy.count("proxy_set_header Host $http_host;") == 4
    for name in SECURITY_HEADERS:
        assert f"add_header {name}" in proxy
    threat_model = (ROOT / "docs" / "THREAT_MODEL.md").read_text(encoding="utf-8")
    for control in ("RBAC", "IDOR", "CSRF", "CSP", "SSRF", "upload", "parser-egress"):
        assert control.casefold() in threat_model.casefold()


def test_same_origin_request_is_allowed_and_cross_origin_preflight_is_denied() -> None:
    with TestClient(
        create_app(settings(), FakeDatabase()), base_url="https://kb.example"
    ) as client:
        allowed = client.get("/health", headers={"Origin": "https://kb.example"})
        denied = client.options(
            "/api/v1/auth/logout",
            headers={
                "Origin": "https://evil.invalid",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert allowed.status_code == 200
    assert denied.status_code == 403
    assert denied.json() == {"detail": {"code": "cross_origin_forbidden"}}
    assert len(denied.headers["X-Request-ID"]) == 36
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.parametrize(
    ("origin", "scheme", "host", "expected"),
    [
        ("https://kb.example", "https", "kb.example", True),
        ("https://kb.example:443", "https", "kb.example", True),
        ("http://kb.example:8080", "http", "kb.example:8080", True),
        ("http://kb.example", "https", "kb.example", False),
        ("https://kb.example.evil.invalid", "https", "kb.example", False),
        ("null", "https", "kb.example", False),
        ("https://user@kb.example", "https", "kb.example", False),
        ("https://kb.example", "https", "user@kb.example", False),
        ("https://kb.example/path", "https", "kb.example", False),
    ],
)
def test_origin_comparison_is_exact(origin: str, scheme: str, host: str, expected: bool) -> None:
    assert is_same_origin(origin, scheme, host) is expected


async def test_import_job_id_does_not_bypass_owner_check() -> None:
    owner_id = uuid4()
    job = ImportJob(
        id=uuid4(),
        source_id=uuid4(),
        submitted_url="https://arduino-tex.ru/news/1/item.html",
        status="queued",
        requested_by=owner_id,
        idempotency_key="safe-key",
        attempts=0,
        max_attempts=4,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = Mock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=job)

    with pytest.raises(HTTPException) as captured:
        await get_import(
            job.id,
            Response(),
            principal(Role.TEACHER),
            cast(AsyncSession, session),
        )
    assert captured.value.status_code == 404
    assert cast(object, captured.value.detail) == {"code": "import_job_not_found"}
