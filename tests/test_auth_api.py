"""Authentication endpoint transaction and cookie regression tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import Request, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.auth import LoginRequest, login
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
async def test_login_returns_server_roles_and_permissions_for_every_role(
    role: Role,
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
    service.settings = settings()
    service.login = AsyncMock(return_value=LoginResult(principal, "opaque-session", "opaque-csrf"))
    session = Mock(spec=AsyncSession)
    session.commit = AsyncMock()
    request = Request({"type": "http", "client": ("127.0.0.1", 12345)})
    response = Response()

    result = await login(
        LoginRequest(login=role.value, password=credential_input),
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
    assert response.headers["cache-control"] == "no-store"
    cookies = response.headers.getlist("set-cookie")
    assert any(
        "ackb_session=opaque-session" in cookie and "HttpOnly" in cookie for cookie in cookies
    )
    assert any(
        "ackb_csrf=opaque-csrf" in cookie and "SameSite=strict" in cookie for cookie in cookies
    )


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
