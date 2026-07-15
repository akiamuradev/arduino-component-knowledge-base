"""Administrator-only user and role management endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.auth import UserResponse
from arduino_component_kb.api.dependencies import (
    auth_service,
    csrf_principal,
    database_session,
    require_roles,
)
from arduino_component_kb.auth.domain import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    LastAdministratorError,
    PasswordPolicyError,
    Principal,
    Role,
    UserAlreadyExistsError,
    UserIdentity,
    normalize_login,
)
from arduino_component_kb.auth.service import AuthService
from arduino_component_kb.logging import current_request_id

router = APIRouter(prefix="/api/v1/admin/users", tags=["administration"])
administrator = require_roles(Role.ADMINISTRATOR)


class CreateUserRequest(BaseModel):
    """Administrator-provided local account data."""

    login: str = Field(min_length=3, max_length=100)
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    roles: set[Role] = Field(default_factory=lambda: {Role.STUDENT}, max_length=3)

    @field_validator("login")
    @classmethod
    def valid_login(cls, value: str) -> str:
        try:
            return normalize_login(value)
        except InvalidCredentialsError as error:
            raise ValueError("login contains unsupported characters") from error

    @field_validator("display_name")
    @classmethod
    def non_blank_display_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("display_name must not be blank")
        return value.strip()


class SetRolesRequest(BaseModel):
    """Complete replacement for a user's role grants."""

    roles: set[Role] = Field(min_length=1, max_length=3)


class MutationResponse(BaseModel):
    """Administrative mutation result."""

    status: str


def identity_response(user: UserIdentity) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        login=user.login,
        display_name=user.display_name,
        roles=sorted(user.roles, key=lambda role: role.value),
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> UserResponse:
    """Create a local user; there is intentionally no public registration."""
    error: Exception | None = None
    user: UserIdentity | None = None
    try:
        user = await service.create_user(
            actor=actor,
            login=payload.login,
            display_name=payload.display_name,
            password=payload.password,
            roles=frozenset(payload.roles),
            request_id=current_request_id(),
        )
    except (UserAlreadyExistsError, PasswordPolicyError) as caught:
        error = caught
    await session.commit()
    if error is not None or user is None:
        raise HTTPException(status_code=409, detail={"code": "user_creation_conflict"})
    return identity_response(user)


@router.put("/{user_id}/roles", response_model=MutationResponse)
async def set_roles(
    user_id: UUID,
    payload: SetRolesRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> MutationResponse:
    """Replace role grants and revoke all target sessions."""
    error: Exception | None = None
    try:
        await service.set_roles(
            actor=actor,
            user_id=user_id,
            roles=frozenset(payload.roles),
            request_id=current_request_id(),
        )
    except (LastAdministratorError, AuthenticationRequiredError) as caught:
        error = caught
    await session.commit()
    if error is not None:
        raise HTTPException(status_code=409, detail={"code": "role_change_conflict"})
    return MutationResponse(status="roles_updated")


@router.post("/{user_id}/disable", response_model=MutationResponse)
async def disable_user(
    user_id: UUID,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> MutationResponse:
    """Disable an account and revoke all of its sessions."""
    error: Exception | None = None
    try:
        await service.disable_user(
            actor=actor,
            user_id=user_id,
            request_id=current_request_id(),
        )
    except (LastAdministratorError, AuthenticationRequiredError) as caught:
        error = caught
    await session.commit()
    if error is not None:
        raise HTTPException(status_code=409, detail={"code": "disable_user_conflict"})
    return MutationResponse(status="disabled")
