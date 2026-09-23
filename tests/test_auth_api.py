"""Authentication endpoint transaction and cookie regression tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Request, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.auth import LoginRequest, RegisterRequest, login, logout, register
from arduino_component_kb.auth.domain import (
    LoginResult,
    Principal,
    Role,
    permissions_for_roles,
)
from arduino_component_kb.auth.service import AuthService
from arduino_component_kb.config import Settings


def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        session_cookie_secure=False,
    )


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("remember", [False, True])
async def test_login_returns_server_roles_and_permissions_for_every_role(
    role: Role,
    remember: bool,
) -> None:
    credential_input = "valid password input"
    principal = Principal(
        user_id=uuid4(),
        login=role.value,
        display_name=role.value,
        roles=frozenset({role}),
        session_id=uuid4(),
        csrf_hash="stored-csrf-hash",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    service = Mock(spec=AuthService)
    service.settings = settings().model_copy(
        update={"session_cookie_secure": True, "remembered_session_ttl_days": 17}
    )
    service.login = AsyncMock(return_value=LoginResult(principal, "opaque-session", "opaque-csrf"))
    session = Mock(spec=AsyncSession)
    session.commit = AsyncMock()
    request = Request({"type": "http", "client": ("127.0.0.1", 12345)})
    response = Response()

    result = await login(
        LoginRequest(login=role.value, password=credential_input, remember=remember),
        request,
        response,
        service,
        session,
    )

    assert result.user.roles == [role]
    assert result.user.permissions == sorted(
        permissions_for_roles(frozenset({role})),
        key=lambda permission: permission.value,
    )
    session.commit.assert_awaited_once()
    assert service.login.await_args.kwargs["remember"] is remember
    assert response.headers["cache-control"] == "no-store"
    cookies = response.headers.getlist("set-cookie")
    assert any(
        "ackb_session=opaque-session" in cookie and "HttpOnly" in cookie for cookie in cookies
    )
    assert any(
        "ackb_csrf=opaque-csrf" in cookie and "SameSite=strict" in cookie for cookie in cookies
    )
    parsed = SimpleCookie()
    for cookie in cookies:
        parsed.load(cookie)
    assert set(parsed) == {"ackb_session", "ackb_csrf"}
    for morsel in parsed.values():
        assert morsel["max-age"] == (str(17 * 86400) if remember else "")
        assert morsel["expires"] == ""
        assert morsel["path"] == "/"
        assert morsel["secure"]
    assert parsed["ackb_session"]["httponly"]
    assert not parsed["ackb_csrf"]["httponly"]
    assert parsed["ackb_session"]["samesite"] == "lax"


def test_old_login_clients_default_to_ordinary_sessions() -> None:
    assert LoginRequest.model_validate({"login": "student", "password": "input"}).remember is False


@pytest.mark.parametrize("days", [0, 91])
def test_remembered_lifetime_is_bounded(days: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, remembered_session_ttl_days=days)


async def test_registration_uses_session_cookies_and_logout_clears_both() -> None:
    principal = Principal(
        uuid4(),
        "student",
        "Student",
        frozenset({Role.STUDENT}),
        uuid4(),
        "csrf-hash",
        datetime.now(UTC) + timedelta(hours=8),
    )
    service = Mock(spec=AuthService)
    service.settings = settings()
    service.register = AsyncMock(return_value=LoginResult(principal, "session", "csrf"))
    service.logout = AsyncMock()
    session = Mock(spec=AsyncSession)
    response = Response()
    credential_input = "test-password-input"
    await register(
        RegisterRequest(login="student", password=credential_input),
        Request({"type": "http", "client": ("127.0.0.1", 12345)}),
        response,
        service,
        session,
    )
    cookies = response.headers.getlist("set-cookie")
    assert len(cookies) == 2
    assert all("Max-Age" not in cookie and "expires=" not in cookie for cookie in cookies)
    assert "remember" not in service.register.await_args.kwargs
    cleared = Response()
    await logout(cleared, principal, service, session)
    service.logout.assert_awaited_once()
    assert service.logout.await_args.args[0] == principal
    for cookie in cleared.headers.getlist("set-cookie"):
        assert "Max-Age=0" in cookie
    assert len(cleared.headers.getlist("set-cookie")) == 2
    assert session.commit.await_count == 2


def test_login_request_rejects_client_supplied_role_or_permissions() -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(
            {
                "login": "student",
                "password": "credential",
                "role": "administrator",
                "permissions": ["system.settings"],
            }
        )


@pytest.mark.parametrize("field", ["role", "roles", "permissions", "display_name"])
def test_register_request_rejects_identity_or_authorization_spoofing(field: str) -> None:
    payload: dict[str, object] = {
        "login": "new-student",
        "password": "safe-student-password",
        field: ["administrator"] if field.endswith("s") else "administrator",
    }
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(payload)


def test_register_request_normalizes_login_and_accepts_only_credentials() -> None:
    request = RegisterRequest.model_validate(
        {"login": "  New.Student  ", "password": "safe-student-password"}
    )
    assert request.model_dump() == {
        "login": "new.student",
        "password": "safe-student-password",
    }
