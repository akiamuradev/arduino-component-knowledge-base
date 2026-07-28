"""Read-only administrator audit log."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import database_session, require_permissions
from arduino_component_kb.auth.domain import AuditRecord, Permission, Principal
from arduino_component_kb.auth.repository import AuthRepository

router = APIRouter(prefix="/api/v1/admin/audit-events", tags=["audit"])
audit_reader = require_permissions(Permission.AUDIT_VIEW)


class AuditActorResponse(BaseModel):
    """Safe actor identity retained after account changes."""

    id: str | None
    type: str
    login: str | None
    display_name: str | None


class AuditObjectResponse(BaseModel):
    """Bounded reference to the affected object."""

    type: str
    id: str | None


class AuditEventResponse(BaseModel):
    """Safe immutable event projection without internal details."""

    id: str
    occurred_at: datetime
    actor: AuditActorResponse
    action: str
    object: AuditObjectResponse
    outcome: str


class AuditEventListResponse(BaseModel):
    """One audit page and the exact available action filters."""

    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int
    available_actions: list[str]


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise HTTPException(422, detail={"code": "audit_date_range_invalid"})
    return value


def _response(record: AuditRecord) -> AuditEventResponse:
    return AuditEventResponse(
        id=str(record.id),
        occurred_at=record.occurred_at,
        actor=AuditActorResponse(
            id=str(record.actor_user_id) if record.actor_user_id is not None else None,
            type=record.actor_type,
            login=record.actor_login,
            display_name=record.actor_display_name,
        ),
        action=record.action,
        object=AuditObjectResponse(
            type=record.object_type,
            id=str(record.object_id) if record.object_id is not None else None,
        ),
        outcome=record.outcome,
    )


@router.get("", response_model=AuditEventListResponse)
async def list_audit_events(
    response: Response,
    _: Annotated[Principal, Depends(audit_reader)],
    session: Annotated[AsyncSession, Depends(database_session)],
    user_id: Annotated[UUID | None, Query()] = None,
    action: Annotated[
        str | None,
        Query(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_.]+$"),
    ] = None,
    occurred_from: Annotated[datetime | None, Query()] = None,
    occurred_to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditEventListResponse:
    """Return immutable events only to a principal with audit.view."""
    safe_from = _aware(occurred_from)
    safe_to = _aware(occurred_to)
    if safe_from is not None and safe_to is not None and safe_to <= safe_from:
        raise HTTPException(422, detail={"code": "audit_date_range_invalid"})
    repository = AuthRepository(session)
    records, total = await repository.list_audit_events(
        actor_user_id=user_id,
        action=action,
        occurred_from=safe_from,
        occurred_to=safe_to,
        limit=limit,
        offset=offset,
    )
    actions = await repository.list_audit_actions()
    response.headers["Cache-Control"] = "no-store"
    return AuditEventListResponse(
        items=[_response(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
        available_actions=list(actions),
    )
