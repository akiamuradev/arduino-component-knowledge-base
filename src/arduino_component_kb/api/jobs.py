"""Administrator-only durable background job monitor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import csrf_principal, database_session, require_roles
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.imports.models import ImportJob
from arduino_component_kb.imports.queue import ImportQueue
from arduino_component_kb.imports.repository import ImportRepository
from arduino_component_kb.logging import current_request_id
from arduino_component_kb.media.domain import MediaJobStatus, MediaKind
from arduino_component_kb.media.models import MediaAsset, MediaJob
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.service import MediaQueue

router = APIRouter(prefix="/api/v1/admin/jobs", tags=["background-jobs"])
administrator = require_roles(Role.ADMINISTRATOR)


class JobResponse(BaseModel):
    id: UUID
    asset_id: UUID
    owner_user_id: UUID
    kind: str
    queue_name: str
    task_name: str
    status: str
    phase: str
    progress_percent: int
    attempts: int
    max_attempts: int
    manual_retry_count: int
    error_code: str | None
    next_retry_at: datetime | None
    heartbeat_at: datetime | None
    last_enqueued_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    limit: int
    offset: int


class JobMutationResponse(BaseModel):
    id: UUID
    status: str


class ImportJobMonitorResponse(BaseModel):
    id: UUID
    requested_by: UUID
    status: str
    attempts: int
    max_attempts: int
    error_code: str | None
    next_retry_at: datetime | None
    heartbeat_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime
    repository_url: str | None
    source_file_path: str | None
    source_entry_name: str | None
    draft_component_id: UUID | None
    retryable: bool


class ImportJobListResponse(BaseModel):
    items: list[ImportJobMonitorResponse]
    total: int
    limit: int
    offset: int


def job_response(job: MediaJob, asset: MediaAsset) -> JobResponse:
    return JobResponse(
        id=job.id,
        asset_id=asset.id,
        owner_user_id=asset.owner_user_id,
        kind=asset.kind,
        queue_name=job.queue_name,
        task_name=job.task_name,
        status=job.status,
        phase=job.phase,
        progress_percent=job.progress_percent,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        manual_retry_count=job.manual_retry_count,
        error_code=job.error_code,
        next_retry_at=job.next_retry_at,
        heartbeat_at=job.heartbeat_at,
        last_enqueued_at=job.last_enqueued_at,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        updated_at=job.updated_at,
    )


def queue_from_request(request: Request) -> MediaQueue:
    return cast(MediaQueue, request.app.state.media_queue)


def import_queue_from_request(request: Request) -> ImportQueue:
    return cast(ImportQueue, request.app.state.import_queue)


def import_job_response(
    job: ImportJob, now: datetime, lease_seconds: int
) -> ImportJobMonitorResponse:
    return ImportJobMonitorResponse(
        id=job.id,
        requested_by=job.requested_by,
        status=job.status,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        error_code=job.error_code,
        next_retry_at=job.next_retry_at,
        heartbeat_at=job.heartbeat_at,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        updated_at=job.updated_at,
        repository_url=job.repository_url,
        source_file_path=job.source_file_path,
        source_entry_name=job.source_entry_name,
        draft_component_id=job.draft_component_id,
        retryable=ImportRepository.is_manually_retryable(job, now, lease_seconds),
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    response: Response,
    _: Annotated[Principal, Depends(administrator)],
    session: Annotated[AsyncSession, Depends(database_session)],
    status: Annotated[MediaJobStatus | None, Query()] = None,
    kind: Annotated[MediaKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobListResponse:
    rows, total = await MediaRepository(session).list_jobs(
        status=status.value if status else None,
        kind=kind.value if kind else None,
        limit=limit,
        offset=offset,
    )
    response.headers["Cache-Control"] = "no-store"
    return JobListResponse(
        items=[job_response(job, asset) for job, asset in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/imports", response_model=ImportJobListResponse)
async def list_import_jobs(
    request: Request,
    response: Response,
    _: Annotated[Principal, Depends(administrator)],
    session: Annotated[AsyncSession, Depends(database_session)],
    status: Annotated[MediaJobStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ImportJobListResponse:
    repository = ImportRepository(session)
    rows, total = await repository.list_jobs(
        status=status.value if status else None,
        limit=limit,
        offset=offset,
    )
    settings = cast(Settings, request.app.state.settings)
    now = datetime.now(UTC)
    response.headers["Cache-Control"] = "no-store"
    return ImportJobListResponse(
        items=[import_job_response(job, now, settings.import_lock_ttl_seconds) for job in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/imports/{job_id}/retry", response_model=JobMutationResponse)
async def retry_import_job(
    job_id: UUID,
    request: Request,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
    queue: Annotated[ImportQueue, Depends(import_queue_from_request)],
) -> JobMutationResponse:
    repository = ImportRepository(session)
    audit = AuthRepository(session)
    now = datetime.now(UTC)
    settings = cast(Settings, request.app.state.settings)
    job = await repository.get_job(job_id, lock=True)
    if job is None:
        raise HTTPException(404, detail={"code": "job_not_found"})
    try:
        reset = repository.prepare_manual_retry(job, now, settings.import_lock_ttl_seconds)
    except ValueError as error:
        raise HTTPException(409, detail={"code": "job_not_retryable"}) from error
    await audit.audit(
        now=now,
        actor_user_id=actor.user_id,
        action="import.job_retry_requested",
        object_type="import_job",
        object_id=job.id,
        request_id=current_request_id(),
        outcome="success",
        details={"reset": reset},
    )
    await session.commit()
    try:
        queue.enqueue(job.id)
    except Exception as error:
        failure_time = datetime.now(UTC)
        failed = await repository.get_job(job.id, lock=True)
        if failed is not None:
            failed.status = "failed"
            failed.error_code = "import_enqueue_failed"
            failed.finished_at = failure_time
            failed.updated_at = failure_time
            failed.heartbeat_at = failure_time
        await audit.audit(
            now=failure_time,
            actor_user_id=actor.user_id,
            action="import.job_enqueue_failed",
            object_type="import_job",
            object_id=job.id,
            request_id=current_request_id(),
            outcome="error",
            details={"code": "import_enqueue_failed"},
        )
        await session.commit()
        raise HTTPException(503, detail={"code": "import_enqueue_failed"}) from error
    return JobMutationResponse(id=job.id, status="queued")


@router.post("/{job_id}/retry", response_model=JobMutationResponse)
async def retry_job(
    job_id: UUID,
    actor: Annotated[Principal, Depends(administrator)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
    queue: Annotated[MediaQueue, Depends(queue_from_request)],
) -> JobMutationResponse:
    repository = MediaRepository(session)
    audit = AuthRepository(session)
    now = datetime.now(UTC)
    row = await repository.lock_job(job_id)
    if row is None:
        raise HTTPException(404, detail={"code": "job_not_found"})
    job, asset = row
    try:
        reset = await repository.prepare_manual_retry(job, asset, now)
    except ValueError as error:
        raise HTTPException(409, detail={"code": "job_not_retryable"}) from error
    await audit.audit(
        now=now,
        actor_user_id=actor.user_id,
        action="media.job_retry_requested",
        object_type="media_job",
        object_id=job.id,
        request_id=current_request_id(),
        outcome="success",
        details={"reset": reset},
    )
    await session.commit()
    try:
        queue.enqueue(job.id, MediaKind(asset.kind))
    except Exception as error:
        failure_time = datetime.now(UTC)
        await audit.audit(
            now=failure_time,
            actor_user_id=actor.user_id,
            action="media.job_enqueue_failed",
            object_type="media_job",
            object_id=job.id,
            request_id=current_request_id(),
            outcome="error",
            details={"code": "media_enqueue_failed"},
        )
        await session.commit()
        raise HTTPException(503, detail={"code": "media_enqueue_failed"}) from error
    await repository.mark_enqueued(job.id, datetime.now(UTC))
    await session.commit()
    return JobMutationResponse(id=job.id, status=MediaJobStatus.QUEUED.value)
