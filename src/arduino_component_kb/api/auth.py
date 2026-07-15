"""Opaque session authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    auth_service,
    csrf_principal,
    current_principal,
    database_session,
)
from arduino_component_kb.auth.domain import (
    InvalidCredentialsError,
    LoginResult,
    Principal,
    Role,
    TooManyAttemptsError,
)
from arduino_component_kb.auth.service import AuthService
from arduino_component_kb.config import Settings
from arduino_component_kb.logging import current_request_id

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    """Bounded local login input."""

    login: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    """Safe authenticated identity response."""

    id: str
    login: str
    display_name: str
    roles: list[Role]


class LoginResponse(BaseModel):
    """Login response without raw session material."""

    user: UserResponse
    expires_at: str


class LogoutResponse(BaseModel):
    """Explicit logout result."""

    status: str = "logged_out"


def user_response(principal: Principal) -> UserResponse:
    return UserResponse(
        id=str(principal.user_id),
        login=principal.login,
        display_name=principal.display_name,
        roles=sorted(principal.roles, key=lambda role: role.value),
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> LoginResponse:
    """Authenticate local credentials and set revocable secure cookies."""
    client_identifier = request.client.host if request.client else "unknown"
    error: Exception | None = None
    result: LoginResult | None = None
    try:
        result = await service.login(
            login=payload.login,
            password=payload.password,
            client_identifier=client_identifier,
            request_id=current_request_id(),
        )
    except (InvalidCredentialsError, TooManyAttemptsError) as caught:
        error = caught
    await session.commit()
    if isinstance(error, TooManyAttemptsError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "authentication_rate_limited"},
            headers={"Retry-After": str(service.settings.auth_block_seconds)},
        )
    if error is not None or result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials"},
        )
    _set_session_cookies(response, result, service.settings)
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(
        user=user_response(result.principal),
        expires_at=result.principal.expires_at.isoformat(),
    )


@router.get("/me", response_model=UserResponse)
async def me(
    response: Response,
    principal: Annotated[Principal, Depends(current_principal)],
) -> UserResponse:
    """Return the backend-resolved principal."""
    response.headers["Cache-Control"] = "no-store"
    return user_response(principal)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    principal: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> LogoutResponse:
    """Revoke the current session and clear both cookies."""
    await service.logout(principal, current_request_id())
    await session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return LogoutResponse()


def _set_session_cookies(response: Response, result: LoginResult, settings: Settings) -> None:
    max_age = settings.session_ttl_minutes * 60
    response.set_cookie(
        SESSION_COOKIE,
        result.session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        result.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )
