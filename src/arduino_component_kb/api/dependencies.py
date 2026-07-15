"""Database, authentication, CSRF, and RBAC dependencies."""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, cast

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.auth.domain import AuthenticationRequiredError, Principal, Role
from arduino_component_kb.auth.passwords import PasswordManager
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.auth.service import AuthService, token_hash
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database

SESSION_COOKIE = "ackb_session"
CSRF_COOKIE = "ackb_csrf"
CSRF_HEADER = "X-CSRF-Token"


async def database_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async session without implicit commit."""
    database = cast(Database, request.app.state.database)
    async with database.sessions() as session:
        yield session


def auth_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(database_session)],
) -> AuthService:
    """Build the auth service around a caller-owned transaction."""
    return AuthService(
        AuthRepository(session),
        cast(Settings, request.app.state.settings),
        cast(PasswordManager, request.app.state.password_manager),
    )


async def current_principal(
    service: Annotated[AuthService, Depends(auth_service)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Principal:
    """Resolve an opaque cookie to an active backend principal."""
    try:
        return await service.authenticate(session_token)
    except AuthenticationRequiredError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required"},
            headers={"WWW-Authenticate": "Session"},
        ) from error


async def csrf_principal(
    principal: Annotated[Principal, Depends(current_principal)],
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> Principal:
    """Require double-submit CSRF material bound to the server-side session."""
    if (
        csrf_cookie is None
        or csrf_header is None
        or len(csrf_header) > 256
        or not hmac.compare_digest(csrf_cookie, csrf_header)
        or not hmac.compare_digest(token_hash(csrf_header), principal.csrf_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "csrf_validation_failed"},
        )
    return principal


def require_roles(*allowed: Role) -> Callable[[Principal], Awaitable[Principal]]:
    """Create a default-deny backend role dependency."""

    async def dependency(
        principal: Annotated[Principal, Depends(current_principal)],
    ) -> Principal:
        if principal.roles.isdisjoint(allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "permission_denied"},
            )
        return principal

    return dependency
