"""Administrator-only user and role management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.auth import UserResponse
from arduino_component_kb.api.dependencies import (
    auth_service,
    csrf_principal,
    database_session,
    require_permissions,
)
from arduino_component_kb.auth.domain import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    LastAdministratorError,
    ManagedUserIdentity,
    PasswordPolicyError,
    Permission,
    Principal,
    Role,
    RoleGrantPolicyError,
    UserAlreadyExistsError,
    UserIdentity,
    normalize_login,
    permissions_for_roles,
)
from arduino_component_kb.auth.service import AuthService
from arduino_component_kb.logging import current_request_id

router = APIRouter(prefix="/api/v1/admin/users", tags=["administration"])
administrator = require_permissions(Permission.USERS_MANAGE, Permission.ROLES_ASSIGN)
user_reader = require_permissions(Permission.USERS_VIEW)


class CreateUserRequest(BaseModel):
    """Administrator-provided local account data."""

    login: str = Field(min_length=3, max_length=100)
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    roles: set[Role] = Field(default_factory=lambda: {Role.STUDENT}, max_length=4)
    editor_expires_at: datetime | None = None

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

    roles: set[Role] = Field(min_length=1, max_length=4)
    editor_expires_at: datetime | None = None


class CreateEditorRequest(BaseModel):
    """Temporary editor account input without a client-controlled role field."""

    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=3, max_length=100)
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    editor_expires_at: datetime

    @field_validator("login")
    @classmethod
    def valid_login(cls, value: str) -> str:
        return CreateUserRequest.valid_login(value)

    @field_validator("display_name")
    @classmethod
    def non_blank_display_name(cls, value: str) -> str:
        return CreateUserRequest.non_blank_display_name(value)


class CreateAdministratorRequest(BaseModel):
    """Administrator creation input with a server-owned role and display name."""

    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("login")
    @classmethod
    def valid_login(cls, value: str) -> str:
        return CreateUserRequest.valid_login(value)


class ResetPasswordRequest(BaseModel):
    """One replacement password without role or profile input."""

    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=12, max_length=128)


class EditorGrantRequest(BaseModel):
    """One temporary editor lifetime without role replacement."""

    model_config = ConfigDict(extra="forbid")

    editor_expires_at: datetime


class ManagedUserResponse(BaseModel):
    """Safe administrator-facing account state."""

    id: str
    login: str
    display_name: str
    status: str
    roles: list[Role]
    editor_expires_at: datetime | None


class ManagedUserListResponse(BaseModel):
    """User-management collection."""

    items: list[ManagedUserResponse]
    total: int


class MutationResponse(BaseModel):
    """Administrative mutation result."""

    status: str


def identity_response(user: UserIdentity) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        login=user.login,
        display_name=user.display_name,
        roles=sorted(user.roles, key=lambda role: role.value),
        permissions=sorted(
            permissions_for_roles(user.roles),
            key=lambda permission: permission.value,
        ),
    )


def managed_identity_response(user: ManagedUserIdentity) -> ManagedUserResponse:
    return ManagedUserResponse(
        id=str(user.id),
        login=user.login,
        display_name=user.display_name,
        status=user.status.value,
        roles=sorted(user.roles, key=lambda role: role.value),
        editor_expires_at=user.editor_expires_at,
    )


@router.get("", response_model=ManagedUserListResponse)
async def list_users(
    response: Response,
    _: Annotated[Principal, Depends(user_reader)],
    service: Annotated[AuthService, Depends(auth_service)],
) -> ManagedUserListResponse:
    """List safe account state for administrator management."""
    users = await service.list_users()
    response.headers["Cache-Control"] = "no-store"
    return ManagedUserListResponse(
        items=[managed_identity_response(user) for user in users],
        total=len(users),
    )


@router.get("/administrators", response_model=ManagedUserListResponse)
async def list_administrators(
    response: Response,
    _: Annotated[Principal, Depends(administrator)],
    service: Annotated[AuthService, Depends(auth_service)],
) -> ManagedUserListResponse:
    """List active administrators in the dedicated administration workspace."""
    users = await service.list_administrators()
    response.headers["Cache-Control"] = "no-store"
    return ManagedUserListResponse(
        items=[managed_identity_response(user) for user in users],
        total=len(users),
    )


@router.post(
    "/administrators",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_administrator(
    payload: CreateAdministratorRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> UserResponse:
    """Create an administrator with a role assigned exclusively by the server."""
    error: Exception | None = None
    user: UserIdentity | None = None
    try:
        user = await service.create_administrator(
            actor=actor,
            login=payload.login,
            password=payload.password,
            request_id=current_request_id(),
        )
    except (UserAlreadyExistsError, PasswordPolicyError) as caught:
        error = caught
    await session.commit()
    if error is not None or user is None:
        raise HTTPException(status_code=409, detail={"code": "administrator_creation_conflict"})
    return identity_response(user)


@router.post("/editors", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_editor(
    payload: CreateEditorRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> UserResponse:
    """Create a temporary editor with a permanent safe student baseline."""
    error: Exception | None = None
    user: UserIdentity | None = None
    try:
        user = await service.create_user(
            actor=actor,
            login=payload.login,
            display_name=payload.display_name,
            password=payload.password,
            roles=frozenset({Role.STUDENT, Role.EDITOR}),
            request_id=current_request_id(),
            editor_expires_at=payload.editor_expires_at,
        )
    except (UserAlreadyExistsError, PasswordPolicyError, RoleGrantPolicyError) as caught:
        error = caught
    await session.commit()
    if error is not None or user is None:
        raise HTTPException(status_code=409, detail={"code": "editor_creation_conflict"})
    return identity_response(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> UserResponse:
    """Create a managed local user while reserving administrator creation."""
    if Role.ADMINISTRATOR in payload.roles:
        raise HTTPException(
            status_code=409,
            detail={"code": "administrator_creation_requires_dedicated_action"},
        )
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
            editor_expires_at=payload.editor_expires_at,
        )
    except (UserAlreadyExistsError, PasswordPolicyError, RoleGrantPolicyError) as caught:
        error = caught
    await session.commit()
    if error is not None or user is None:
        raise HTTPException(status_code=409, detail={"code": "user_creation_conflict"})
    return identity_response(user)


@router.put("/{user_id}/password", response_model=MutationResponse)
async def reset_password(
    user_id: UUID,
    payload: ResetPasswordRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> MutationResponse:
    """Replace a user's password and revoke all of that user's sessions."""
    error: Exception | None = None
    try:
        await service.reset_password(
            actor=actor,
            user_id=user_id,
            password=payload.password,
            request_id=current_request_id(),
        )
    except (AuthenticationRequiredError, PasswordPolicyError) as caught:
        error = caught
    await session.commit()
    if error is not None:
        raise HTTPException(status_code=409, detail={"code": "password_reset_conflict"})
    return MutationResponse(status="password_reset")


@router.put("/{user_id}/editor", response_model=MutationResponse)
async def grant_editor(
    user_id: UUID,
    payload: EditorGrantRequest,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> MutationResponse:
    """Grant or renew editor access without accepting a role from the client."""
    error: Exception | None = None
    try:
        await service.grant_editor(
            actor=actor,
            user_id=user_id,
            expires_at=payload.editor_expires_at,
            request_id=current_request_id(),
        )
    except (AuthenticationRequiredError, RoleGrantPolicyError) as caught:
        error = caught
    await session.commit()
    if error is not None:
        raise HTTPException(status_code=409, detail={"code": "editor_grant_conflict"})
    return MutationResponse(status="editor_granted")


@router.delete("/{user_id}/editor", response_model=MutationResponse)
async def revoke_editor(
    user_id: UUID,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[AuthService, Depends(auth_service)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> MutationResponse:
    """Revoke active editor access early and preserve its grant history."""
    error: Exception | None = None
    try:
        await service.revoke_editor(
            actor=actor,
            user_id=user_id,
            request_id=current_request_id(),
        )
    except (AuthenticationRequiredError, RoleGrantPolicyError) as caught:
        error = caught
    await session.commit()
    if error is not None:
        raise HTTPException(status_code=409, detail={"code": "editor_revoke_conflict"})
    return MutationResponse(status="editor_revoked")


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
            editor_expires_at=payload.editor_expires_at,
        )
    except (
        LastAdministratorError,
        AuthenticationRequiredError,
        RoleGrantPolicyError,
    ) as caught:
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
