"""Teacher import API backed by durable parser jobs."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import csrf_principal, database_session, require_roles
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.config import Settings
from arduino_component_kb.imports.domain import SourcePolicyError
from arduino_component_kb.imports.models import ImportJob
from arduino_component_kb.imports.queue import ImportQueue
from arduino_component_kb.imports.repository import ImportRepository
from arduino_component_kb.imports.urls import approve_source_url

router = APIRouter(prefix="/api/v1/import-jobs", tags=["imports"])
editor = require_roles(Role.TEACHER, Role.ADMINISTRATOR)


class ImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=1000)


class ImportJobResponse(BaseModel):
    id: UUID
    submitted_url: str
    canonical_url: str | None
    status: str
    attempts: int
    max_attempts: int
    parser_version: str | None
    draft_component_id: UUID | None
    error_code: str | None


def _response(job: ImportJob) -> ImportJobResponse:
    return ImportJobResponse.model_validate(job, from_attributes=True)


def queue_from_request(request: Request) -> ImportQueue:
    return cast(ImportQueue, request.app.state.import_queue)


@router.post("", response_model=ImportJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_import(
    payload: ImportRequest,
    request: Request,
    response: Response,
    actor: Annotated[Principal, Depends(editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
    queue: Annotated[ImportQueue, Depends(queue_from_request)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)],
) -> ImportJobResponse:
    try:
        approved = approve_source_url(payload.url)
    except SourcePolicyError as error:
        raise HTTPException(422, detail={"code": str(error)}) from error
    repository = ImportRepository(session)
    source = await repository.source_for_host(approved.host)
    if source is None:
        raise HTTPException(422, detail={"code": "source_disabled"})
    job = await repository.get_idempotent_job(actor.user_id, idempotency_key)
    if job is None:
        settings = cast(Settings, request.app.state.settings)
        job = repository.add_job(
            source,
            approved.url,
            actor.user_id,
            idempotency_key,
            settings.import_job_max_attempts,
        )
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            job = await repository.get_idempotent_job(actor.user_id, idempotency_key)
            if job is None:
                raise
    if job.submitted_url != approved.url:
        await session.rollback()
        raise HTTPException(409, detail={"code": "idempotency_key_conflict"})
    await session.commit()
    if job.status in {"queued", "retrying"}:
        try:
            queue.enqueue(job.id)
        except Exception as error:
            raise HTTPException(503, detail={"code": "import_enqueue_failed"}) from error
    response.headers["Cache-Control"] = "no-store"
    return _response(job)


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_import(
    job_id: UUID,
    response: Response,
    actor: Annotated[Principal, Depends(editor)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ImportJobResponse:
    job = await ImportRepository(session).get_job(job_id)
    if job is None or (
        Role.ADMINISTRATOR not in actor.roles and job.requested_by != actor.user_id
    ):
        raise HTTPException(404, detail={"code": "import_job_not_found"})
    response.headers["Cache-Control"] = "no-store"
    return _response(job)
