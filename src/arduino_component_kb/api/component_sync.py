"""Atomic editor sync and lifecycle commands with authoritative edit tokens."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.catalog import (
    ComponentResponse,
    CreateDraftRequest,
    _error,
    response,
)
from arduino_component_kb.api.dependencies import (
    csrf_principal,
    database_session,
    require_permissions,
)
from arduino_component_kb.auth.domain import Permission, Principal
from arduino_component_kb.catalog.domain import CatalogError, ComponentStatus
from arduino_component_kb.catalog.operations import CatalogLifecycleOperations
from arduino_component_kb.catalog.synchronization import DocumentSynchronization
from arduino_component_kb.logging import current_request_id

router = APIRouter(prefix="/api/v1/workspace", tags=["editor-sync"])
creator = require_permissions(Permission.COMPONENTS_CREATE)
editor = require_permissions(Permission.COMPONENTS_EDIT)
publisher = require_permissions(Permission.COMPONENTS_REVIEW, Permission.COMPONENTS_PUBLISH)


class CreateDocumentRequest(CreateDraftRequest):
    creation_key: UUID


class SyncDocumentRequest(CreateDraftRequest):
    edit_token: int = Field(ge=1)


class TokenRequest(BaseModel):
    edit_token: int = Field(ge=1)


Command = Literal["submit", "request-changes", "publish", "hide", "show", "archive", "restore"]
COMMANDS = {
    "submit": (Permission.COMPONENTS_SUBMIT_FOR_REVIEW, ComponentStatus.IN_REVIEW),
    "request-changes": (Permission.COMPONENTS_REVIEW, ComponentStatus.CHANGES_REQUESTED),
    "publish": (Permission.COMPONENTS_PUBLISH, ComponentStatus.PUBLISHED),
    "hide": (Permission.COMPONENTS_PUBLISH, ComponentStatus.HIDDEN),
    "show": (Permission.COMPONENTS_PUBLISH, ComponentStatus.PUBLISHED),
    "archive": (Permission.COMPONENTS_ARCHIVE, ComponentStatus.ARCHIVED),
    "restore": (Permission.COMPONENTS_ARCHIVE, ComponentStatus.DRAFT),
}


@router.post("/editor-drafts", response_model=ComponentResponse, status_code=201)
async def create_document(
    payload: CreateDocumentRequest,
    actor: Annotated[Principal, Depends(creator)],
    csrf: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ComponentResponse:
    try:
        if payload.images:
            raise HTTPException(422, detail={"code": "create_then_attach_images"})
        card = await DocumentSynchronization(session).create(
            payload.creation_key,
            payload.domain(),
            actor.user_id,
        )
        await session.commit()
        return response(card)
    except (CatalogError, IntegrityError) as error:
        await session.rollback()
        raise _error(error) from error


@router.put("/components/{component_id}/sync", response_model=ComponentResponse)
async def synchronize_document(
    component_id: UUID,
    payload: SyncDocumentRequest,
    actor: Annotated[Principal, Depends(editor)],
    csrf: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ComponentResponse:
    try:
        card = await DocumentSynchronization(session).synchronize(
            component_id,
            payload.edit_token,
            payload.domain(),
            tuple(image.domain() for image in payload.images),
            payload.primary_asset_id,
            actor.user_id,
        )
        await session.commit()
        return response(card)
    except (CatalogError, IntegrityError) as error:
        await session.rollback()
        raise _error(error) from error


@router.post("/components/{component_id}/approve-and-publish", response_model=ComponentResponse)
async def approve_and_publish(
    component_id: UUID,
    payload: TokenRequest,
    actor: Annotated[Principal, Depends(publisher)],
    csrf: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ComponentResponse:
    try:
        card = await DocumentSynchronization(session).approve_and_publish(
            component_id,
            payload.edit_token,
            actor.user_id,
        )
        await session.commit()
        return response(card)
    except (CatalogError, IntegrityError) as error:
        await session.rollback()
        raise _error(error) from error


@router.post("/components/{component_id}/commands/{action}", response_model=ComponentResponse)
async def document_command(
    component_id: UUID,
    action: Command,
    payload: TokenRequest,
    actor: Annotated[Principal, Depends(editor)],
    csrf: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ComponentResponse:
    permission, target = COMMANDS[action]
    if not actor.can(permission):
        raise HTTPException(403, detail={"code": "permission_denied"})
    try:
        row = await DocumentSynchronization(session).lock(component_id, payload.edit_token)
        operations = CatalogLifecycleOperations(session)
        if action == "show":
            card = await operations.show_hidden(
                component_id, row.revision, actor.user_id, current_request_id()
            )
        elif action == "restore":
            card = await operations.restore_archived(
                component_id, row.revision, actor.user_id, current_request_id()
            )
        else:
            card = await operations.transition(
                component_id, row.revision, target, actor.user_id, current_request_id()
            )
        return response(card)
    except (CatalogError, IntegrityError) as error:
        await session.rollback()
        raise _error(error) from error
