"""Executable browser-boundary and mutation authorization contracts."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, _IncludedRouter
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import (
    CSRF_COOKIE,
    CSRF_HEADER,
    csrf_principal,
    current_principal,
)
from arduino_component_kb.api.imports import get_import
from arduino_component_kb.api.imports import router as imports_router
from arduino_component_kb.api.jobs import retry_import_job
from arduino_component_kb.auth.domain import Permission, Principal, Role
from arduino_component_kb.auth.service import token_hash
from arduino_component_kb.config import Settings
from arduino_component_kb.imports.models import ImportJob
from arduino_component_kb.main import create_app
from arduino_component_kb.security import (
    CONTENT_SECURITY_POLICY,
    SECURITY_HEADERS,
    is_same_origin,
    is_trusted_host,
)

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
        trusted_hosts="testserver,kb.example",
    )


def principal(role: Role, *, user_id: UUID | None = None) -> Principal:
    return Principal(
        user_id=user_id or uuid4(),
        login="user",
        display_name="User",
        roles=frozenset({role}),
        session_id=uuid4(),
        csrf_hash=token_hash("csrf-value"),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _dependency_calls(dependant: Dependant) -> Iterator[Callable[..., object]]:
    for child in dependant.dependencies:
        if child.call is not None:
            yield child.call
        yield from _dependency_calls(child)


def _effective_api_routes(
    app: FastAPI,
) -> Iterator[tuple[frozenset[str], str, Dependant]]:
    """Walk direct and lazily included FastAPI routes without silently skipping either."""
    for route in app.routes:
        if isinstance(route, APIRoute):
            yield frozenset(route.methods or ()), route.path, route.dependant
            continue
        if not isinstance(route, _IncludedRouter):
            continue
        for context in route.effective_route_contexts():
            if not isinstance(context.original_route, APIRoute):
                continue
            assert context.dependant is not None
            yield frozenset(context.methods), context.path, context.dependant


def _permission_set(dependant: Dependant) -> frozenset[Permission] | None:
    declared = [
        frozenset(cast(frozenset[Permission], permissions))
        for call in _dependency_calls(dependant)
        if (permissions := inspect.getclosurevars(call).nonlocals.get("required_set")) is not None
    ]
    if not declared:
        return None
    assert len(declared) == 1
    return declared[0]


ROUTE_PERMISSIONS: dict[tuple[str, str], frozenset[Permission]] = {
    ("GET", "/api/v1/admin/audit-events"): frozenset({Permission.AUDIT_VIEW}),
    ("GET", "/api/v1/admin/users"): frozenset({Permission.USERS_VIEW}),
    ("POST", "/api/v1/admin/users/editors"): frozenset(
        {Permission.USERS_MANAGE, Permission.ROLES_ASSIGN}
    ),
    ("POST", "/api/v1/admin/users"): frozenset({Permission.USERS_MANAGE, Permission.ROLES_ASSIGN}),
    ("PUT", "/api/v1/admin/users/{user_id}/editor"): frozenset(
        {Permission.USERS_MANAGE, Permission.ROLES_ASSIGN}
    ),
    ("DELETE", "/api/v1/admin/users/{user_id}/editor"): frozenset(
        {Permission.USERS_MANAGE, Permission.ROLES_ASSIGN}
    ),
    ("PUT", "/api/v1/admin/users/{user_id}/roles"): frozenset(
        {Permission.USERS_MANAGE, Permission.ROLES_ASSIGN}
    ),
    ("POST", "/api/v1/admin/users/{user_id}/disable"): frozenset(
        {Permission.USERS_MANAGE, Permission.ROLES_ASSIGN}
    ),
    ("GET", "/api/v1/admin/jobs"): frozenset({Permission.SYSTEM_DIAGNOSTICS}),
    ("GET", "/api/v1/admin/jobs/imports"): frozenset({Permission.SYSTEM_DIAGNOSTICS}),
    ("POST", "/api/v1/admin/jobs/imports/{job_id}/retry"): frozenset({Permission.IMPORTS_RETRY}),
    ("POST", "/api/v1/admin/jobs/{job_id}/retry"): frozenset({Permission.SYSTEM_DIAGNOSTICS}),
    ("POST", "/api/v1/media/images/uploads"): frozenset({Permission.COMPONENTS_EDIT}),
    ("POST", "/api/v1/media/images/{asset_id}/complete"): frozenset({Permission.COMPONENTS_EDIT}),
    ("GET", "/api/v1/media/images/{asset_id}"): frozenset({Permission.COMPONENTS_EDIT}),
    ("POST", "/api/v1/media/videos/uploads"): frozenset({Permission.COMPONENTS_EDIT}),
    ("POST", "/api/v1/media/videos/{asset_id}/complete"): frozenset({Permission.COMPONENTS_EDIT}),
    ("GET", "/api/v1/media/videos/{asset_id}"): frozenset({Permission.COMPONENTS_EDIT}),
    ("POST", "/api/v1/import-jobs"): frozenset({Permission.IMPORTS_CREATE}),
    ("GET", "/api/v1/import-jobs"): frozenset({Permission.IMPORTS_VIEW}),
    ("GET", "/api/v1/import-jobs/repository/discovery"): frozenset({Permission.IMPORTS_CREATE}),
    ("GET", "/api/v1/import-jobs/repository/entries"): frozenset({Permission.IMPORTS_CREATE}),
    ("POST", "/api/v1/import-jobs/repository/preview"): frozenset({Permission.IMPORTS_CREATE}),
    ("POST", "/api/v1/import-jobs/repository"): frozenset({Permission.IMPORTS_CREATE}),
    ("POST", "/api/v1/import-jobs/{job_id}/retry"): frozenset({Permission.IMPORTS_RETRY}),
    ("POST", "/api/v1/import-jobs/{job_id}/cancel"): frozenset({Permission.IMPORTS_CANCEL}),
    ("GET", "/api/v1/import-jobs/{job_id}"): frozenset({Permission.IMPORTS_VIEW}),
    ("GET", "/api/v1/admin/import-reviews"): frozenset({Permission.COMPONENTS_REVIEW}),
    ("GET", "/api/v1/admin/import-reviews/{review_draft_id}"): frozenset(
        {Permission.COMPONENTS_REVIEW}
    ),
    (
        "POST",
        "/api/v1/admin/import-reviews/{review_draft_id}/enrichments/{enrichment_id}/decision",
    ): frozenset({Permission.COMPONENTS_REVIEW}),
    (
        "POST",
        "/api/v1/admin/import-reviews/{review_draft_id}/enrichments/{enrichment_id}/relation",
    ): frozenset({Permission.COMPONENTS_REVIEW}),
    (
        "POST",
        "/api/v1/admin/import-reviews/{review_draft_id}/identity",
    ): frozenset({Permission.COMPONENTS_REVIEW}),
    (
        "POST",
        "/api/v1/admin/import-reviews/{review_draft_id}/specification-mappings",
    ): frozenset({Permission.COMPONENTS_REVIEW}),
    (
        "POST",
        "/api/v1/admin/import-reviews/{review_draft_id}/parser-issues",
    ): frozenset({Permission.COMPONENTS_REVIEW}),
    (
        "POST",
        "/api/v1/admin/import-reviews/{review_draft_id}/confirm",
    ): frozenset({Permission.COMPONENTS_REVIEW}),
    ("GET", "/api/v1/workspace/categories"): frozenset({Permission.COMPONENTS_EDIT}),
    ("GET", "/api/v1/workspace/components"): frozenset({Permission.COMPONENTS_EDIT}),
    ("GET", "/api/v1/workspace/components/{component_id}"): frozenset({Permission.COMPONENTS_EDIT}),
    ("GET", "/api/v1/workspace/components/{component_id}/history"): frozenset(
        {Permission.COMPONENTS_EDIT}
    ),
    ("POST", "/api/v1/workspace/components"): frozenset({Permission.COMPONENTS_CREATE}),
    ("PUT", "/api/v1/workspace/components/{component_id}"): frozenset({Permission.COMPONENTS_EDIT}),
    ("PUT", "/api/v1/workspace/components/{component_id}/images"): frozenset(
        {Permission.COMPONENTS_EDIT}
    ),
    (
        "POST",
        "/api/v1/workspace/components/{component_id}/submit-for-review",
    ): frozenset({Permission.COMPONENTS_SUBMIT_FOR_REVIEW}),
    (
        "POST",
        "/api/v1/workspace/components/{component_id}/request-changes",
    ): frozenset({Permission.COMPONENTS_REVIEW}),
    ("POST", "/api/v1/workspace/components/{component_id}/approve"): frozenset(
        {Permission.COMPONENTS_REVIEW}
    ),
    ("POST", "/api/v1/workspace/components/{component_id}/publish"): frozenset(
        {Permission.COMPONENTS_PUBLISH}
    ),
    ("POST", "/api/v1/workspace/components/{component_id}/hide"): frozenset(
        {Permission.COMPONENTS_PUBLISH}
    ),
    ("POST", "/api/v1/workspace/components/{component_id}/show"): frozenset(
        {Permission.COMPONENTS_PUBLISH}
    ),
    ("POST", "/api/v1/workspace/components/{component_id}/archive"): frozenset(
        {Permission.COMPONENTS_ARCHIVE}
    ),
    ("POST", "/api/v1/workspace/components/{component_id}/restore"): frozenset(
        {Permission.COMPONENTS_ARCHIVE}
    ),
    ("POST", "/api/v1/admin/catalog/categories"): frozenset({Permission.SYSTEM_SETTINGS}),
    ("POST", "/api/v1/admin/catalog/categories/{category_id}/deactivate"): frozenset(
        {Permission.SYSTEM_SETTINGS}
    ),
    ("GET", "/api/v1/catalog/categories"): frozenset({Permission.COMPONENTS_VIEW}),
    ("GET", "/api/v1/catalog/sources"): frozenset({Permission.COMPONENTS_VIEW}),
    ("GET", "/api/v1/catalog/components"): frozenset({Permission.COMPONENTS_VIEW}),
    ("GET", "/api/v1/catalog/components/{slug}"): frozenset({Permission.COMPONENTS_VIEW}),
    ("GET", "/api/v1/admin/duplicates"): frozenset({Permission.COMPONENTS_REVIEW}),
    ("GET", "/api/v1/admin/duplicates/{candidate_id}"): frozenset({Permission.COMPONENTS_REVIEW}),
    ("POST", "/api/v1/admin/duplicates/{candidate_id}/decision"): frozenset(
        {Permission.COMPONENTS_REVIEW}
    ),
}


def test_every_authenticated_mutation_requires_csrf() -> None:
    app = create_app(settings(), FakeDatabase())
    missing: list[str] = []
    for methods, path, dependant in _effective_api_routes(app):
        if not methods.intersection({"POST", "PUT", "PATCH", "DELETE"}):
            continue
        if path == "/api/v1/auth/login":
            continue
        if csrf_principal not in set(_dependency_calls(dependant)):
            missing.append(f"{','.join(sorted(methods))} {path}")
    assert missing == []


def test_authentication_has_no_public_registration_route() -> None:
    app = create_app(settings(), FakeDatabase())
    paths = {path for _, path, _ in _effective_api_routes(app)}
    assert "/api/v1/auth/register" not in paths


def test_sensitive_route_groups_keep_backend_permission_dependencies() -> None:
    app = create_app(settings(), FakeDatabase())
    missing: list[str] = []
    for _, path, dependant in _effective_api_routes(app):
        if not path.startswith(
            (
                "/api/v1/admin",
                "/api/v1/catalog",
                "/api/v1/workspace",
                "/api/v1/media",
                "/api/v1/import-jobs",
            )
        ):
            continue
        if _permission_set(dependant) is None:
            missing.append(path)
    assert missing == []


def test_every_protected_route_has_exact_server_permission_contract() -> None:
    app = create_app(settings(), FakeDatabase())
    actual: dict[tuple[str, str], frozenset[Permission]] = {}
    for methods, path, dependant in _effective_api_routes(app):
        permissions = _permission_set(dependant)
        if permissions is None:
            continue
        for method in methods:
            actual[(method, path)] = permissions
    assert actual == ROUTE_PERMISSIONS


def test_unimplemented_destructive_actions_are_not_exposed_by_partial_routes() -> None:
    app = create_app(settings(), FakeDatabase())
    routes = {
        (method, path) for methods, path, _ in _effective_api_routes(app) for method in methods
    }
    used_permissions = {
        permission
        for _, _, dependant in _effective_api_routes(app)
        for permission in (_permission_set(dependant) or ())
    }
    assert Permission.COMPONENTS_DELETE not in used_permissions
    assert ("DELETE", "/api/v1/admin/users/{user_id}") not in routes


def test_repository_import_workflow_requires_import_create_permission() -> None:
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
        permission_sets = {
            frozenset(permissions)
            for call in _dependency_calls(route.dependant)
            if (permissions := inspect.getclosurevars(call).nonlocals.get("required_set"))
            is not None
        }
        assert frozenset({Permission.IMPORTS_CREATE}) in permission_sets
        checked.add(route.path)
    assert checked == protected_paths


def _concrete_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid4()), path)


def _override_principal(actor: Principal) -> Callable[[], Principal]:
    def dependency() -> Principal:
        return actor

    return dependency


def test_direct_api_denies_every_role_missing_a_route_permission() -> None:
    app = create_app(settings(), FakeDatabase())
    failures: list[str] = []
    checked_roles: set[Role] = set()
    with TestClient(app) as client:
        client.cookies.set(CSRF_COOKIE, "csrf-value")
        for (method, path), required in ROUTE_PERMISSIONS.items():
            for role in Role:
                actor = principal(role)
                if required.issubset(actor.permissions):
                    continue
                checked_roles.add(role)
                app.dependency_overrides[current_principal] = _override_principal(actor)
                response = client.request(
                    method,
                    _concrete_path(path),
                    headers={CSRF_HEADER: "csrf-value"},
                    json={} if method in {"POST", "PUT", "PATCH", "DELETE"} else None,
                )
                if response.status_code != 403 or response.json()["error"]["code"] != (
                    "permission_denied"
                ):
                    failures.append(f"{role.value} {method} {path}: {response.status_code}")
    app.dependency_overrides.clear()
    assert checked_roles == {Role.STUDENT, Role.TEACHER, Role.EDITOR}
    assert failures == []


def test_administrator_mutation_still_requires_csrf_at_direct_api_boundary() -> None:
    app = create_app(settings(), FakeDatabase())
    app.dependency_overrides[current_principal] = _override_principal(principal(Role.ADMINISTRATOR))
    with TestClient(app) as client:
        response = client.post(f"/api/v1/admin/jobs/{uuid4()}/retry")
    assert response.status_code == 403
    assert response.json()["error"] == {
        "code": "csrf_validation_failed",
        "message": "Сессия устарела. Обновите страницу и повторите действие.",
        "retryable": False,
        "request_id": response.headers["X-Request-ID"],
    }


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
    assert denied.json()["error"] == {
        "code": "cross_origin_forbidden",
        "message": "Запрос с этой страницы недоступен.",
        "retryable": False,
        "request_id": denied.headers["X-Request-ID"],
    }
    assert len(denied.headers["X-Request-ID"]) == 36
    assert "access-control-allow-origin" not in denied.headers


def test_untrusted_host_is_rejected_before_routing() -> None:
    with TestClient(create_app(settings(), FakeDatabase())) as client:
        response = client.get("/health", headers={"Host": "evil.invalid"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "untrusted_host"
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("kb.example", True),
        ("kb.example:443", True),
        ("KB.EXAMPLE.", True),
        ("kb.example.evil.invalid", False),
        ("user@kb.example", False),
        ("kb.example/path", False),
        ("", False),
    ],
)
def test_trusted_host_comparison_is_exact(host: str, expected: bool) -> None:
    assert is_trusted_host(host, frozenset({"kb.example"})) is expected


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
            principal(Role.EDITOR),
            cast(AsyncSession, session),
        )
    assert captured.value.status_code == 404
    assert cast(object, captured.value.detail) == {"code": "import_job_not_found"}


async def test_import_retry_id_does_not_bypass_owner_check() -> None:
    owner_id = uuid4()
    job = ImportJob(
        id=uuid4(),
        source_id=uuid4(),
        submitted_url="https://arduino-tex.ru/news/1/item.html",
        status="failed",
        requested_by=owner_id,
        idempotency_key="safe-retry-key",
        attempts=4,
        max_attempts=4,
        error_code="import_fetch_failed",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = Mock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=job)
    app = create_app(settings(), FakeDatabase())
    request = Request({"type": "http", "app": app})
    actor = principal(Role.EDITOR)

    with pytest.raises(HTTPException) as captured:
        await retry_import_job(
            job.id,
            request,
            actor,
            actor,
            cast(AsyncSession, session),
        )
    assert captured.value.status_code == 404
    assert cast(object, captured.value.detail) == {"code": "job_not_found"}
    assert job.status == "failed"
    session.commit.assert_not_called()
