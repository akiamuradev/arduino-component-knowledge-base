"""Teacher import API backed by durable parser jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import (
    csrf_principal,
    database_session,
    require_permissions,
)
from arduino_component_kb.auth.domain import Permission, Principal
from arduino_component_kb.auth.models import User
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.catalog.models import Component
from arduino_component_kb.config import Settings
from arduino_component_kb.imports.acquisition import (
    AcquisitionPolicy,
    RepositoryAcquirer,
    RepositoryAcquisitionError,
)
from arduino_component_kb.imports.adapters.kicad_symbols import KicadSymbolsAdapter
from arduino_component_kb.imports.adapters.repository import RepositorySourceAdapter
from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.domain import SourcePolicyError
from arduino_component_kb.imports.models import ImportJob, Source
from arduino_component_kb.imports.queue import ImportQueue
from arduino_component_kb.imports.repository import ImportRepository
from arduino_component_kb.imports.repository_domain import (
    ParsedRepositoryComponent,
    RepositoryEntry,
    normalize_repository_path,
)
from arduino_component_kb.imports.urls import approve_source_url
from arduino_component_kb.logging import current_request_id

router = APIRouter(prefix="/api/v1/import-jobs", tags=["imports"])
editor = require_permissions(Permission.IMPORTS_CREATE)
import_viewer = require_permissions(Permission.IMPORTS_VIEW)
import_retry = require_permissions(Permission.IMPORTS_RETRY)
import_cancel = require_permissions(Permission.IMPORTS_CANCEL)


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
    repository_url: str | None
    requested_revision: str | None
    source_revision: str | None
    source_file_path: str | None
    source_entry_name: str | None
    parser_name: str | None
    parse_status: str | None
    warnings_json: list[str]
    heartbeat_at: datetime | None
    metrics_json: dict[str, object]


ImportDisplayStatus = Literal[
    "pending",
    "processing",
    "needs_review",
    "ready",
    "published",
    "error",
    "cancelled",
]


class ImportListItemResponse(BaseModel):
    id: UUID
    title: str
    source: str
    requested_by: str
    created_at: datetime
    status: ImportDisplayStatus
    result: str
    component_id: UUID | None
    can_retry: bool
    can_cancel: bool


class ImportListResponse(BaseModel):
    items: list[ImportListItemResponse]
    total: int
    limit: int
    offset: int


class ImportActionResponse(BaseModel):
    id: UUID
    status: Literal["queued", "cancelled"]


class RepositoryImportRequest(BaseModel):
    source_key: Literal["seeed_wiki", "kicad_symbols"]
    revision: str = Field(min_length=1, max_length=100)
    file_path: str = Field(min_length=1, max_length=1000)
    entry_name: str | None = Field(default=None, min_length=1, max_length=300)


class RepositoryFileResponse(BaseModel):
    file_path: str
    size: int | None


class RepositoryDiscoveryResponse(BaseModel):
    source_key: Literal["seeed_wiki", "kicad_symbols"]
    repository_url: str
    revision: str
    files_scanned: int
    files: list[RepositoryFileResponse]


class RepositoryEntryResponse(BaseModel):
    file_path: str
    entry_name: str | None
    title: str | None


class RepositoryEntryDiscoveryResponse(BaseModel):
    source_key: Literal["seeed_wiki", "kicad_symbols"]
    repository_url: str
    revision: str
    entries: list[RepositoryEntryResponse]


class FieldProvenanceResponse(BaseModel):
    repository_url: str
    source_revision: str
    source_file_path: str
    section_or_property: str
    confidence: str
    transformation: str


class LicenseSnapshotResponse(BaseModel):
    name: str
    spdx: str
    url: str
    attribution: str


class RepositoryPreviewResponse(BaseModel):
    source_key: Literal["seeed_wiki", "kicad_symbols"]
    repository_url: str
    requested_revision: str
    revision: str
    file_path: str
    entry_name: str | None
    original_url: str
    parser_name: str
    parser_version: str
    parse_status: str
    warnings: list[str]
    normalized_fields: dict[str, object]
    provenance: dict[str, list[FieldProvenanceResponse]]
    license: LicenseSnapshotResponse
    modifications_notice: str
    draft_status: Literal["draft"]


def _response(job: ImportJob) -> ImportJobResponse:
    return ImportJobResponse.model_validate(job, from_attributes=True)


def _display_status(job: ImportJob, component_status: str | None) -> ImportDisplayStatus:
    if job.status in {"queued", "retrying"}:
        return "pending"
    if job.status == "running":
        return "processing"
    if job.status == "failed":
        return "error"
    if job.status == "cancelled":
        return "cancelled"
    if component_status == "published":
        return "published"
    if component_status in {"in_review", "changes_requested"} or (
        job.parse_status == "parsed_with_warnings"
    ):
        return "needs_review"
    return "ready"


def _display_result(display_status: ImportDisplayStatus) -> str:
    return {
        "pending": "Ожидает начала обработки",
        "processing": "Идёт обработка материалов",
        "needs_review": "Нужна ручная проверка",
        "ready": "Черновик карточки готов",
        "published": "Карточка опубликована",
        "error": "Компонент не удалось обработать",
        "cancelled": "Загрузка отменена",
    }[display_status]


def _display_title(job: ImportJob, source_name: str) -> str:
    if job.source_entry_name:
        return job.source_entry_name
    if job.source_file_path:
        source_path = PurePosixPath(job.source_file_path)
        return source_path.stem or source_path.name
    return f"Компонент из источника «{source_name}»"


def _list_item(
    job: ImportJob,
    source_name: str,
    requested_by: str,
    component_status: str | None,
    *,
    can_retry: bool,
    can_cancel: bool,
) -> ImportListItemResponse:
    display_status = _display_status(job, component_status)
    return ImportListItemResponse(
        id=job.id,
        title=_display_title(job, source_name),
        source=source_name,
        requested_by=requested_by,
        created_at=job.created_at,
        status=display_status,
        result=_display_result(display_status),
        component_id=job.draft_component_id,
        can_retry=can_retry,
        can_cancel=can_cancel,
    )


def queue_from_request(request: Request) -> ImportQueue:
    return cast(ImportQueue, request.app.state.import_queue)


def _acquirer(settings: Settings) -> RepositoryAcquirer:
    return RepositoryAcquirer(
        policy=AcquisitionPolicy(
            connect_timeout_seconds=settings.repository_connect_timeout_seconds,
            read_timeout_seconds=settings.repository_read_timeout_seconds,
            total_timeout_seconds=settings.repository_total_timeout_seconds,
            max_response_bytes=settings.repository_max_response_bytes,
            max_file_bytes=settings.repository_max_file_bytes,
        )
    )


def _adapter(settings: Settings, source_key: str) -> RepositorySourceAdapter:
    if source_key == "seeed_wiki":
        return SeeedWikiAdapter()
    _require_legacy_kicad_card_import(settings, source_key)
    return KicadSymbolsAdapter(settings.kicad_library_prefixes)


def _require_legacy_kicad_card_import(settings: Settings, source_key: str) -> None:
    if source_key == "kicad_symbols" and not settings.legacy_kicad_card_import_enabled:
        raise ValueError("legacy_kicad_card_import_disabled")


def _validated_entry(payload: RepositoryImportRequest) -> RepositoryEntry:
    try:
        file_path = normalize_repository_path(payload.file_path)
        if payload.source_key == "seeed_wiki" and payload.entry_name is not None:
            raise ValueError("repository_entry_name_not_allowed")
        if payload.source_key == "kicad_symbols" and payload.entry_name is None:
            raise ValueError("repository_entry_name_required")
        return RepositoryEntry(file_path, payload.entry_name)
    except ValueError as error:
        raise HTTPException(422, detail={"code": _safe_value_code(error)}) from error


def _safe_value_code(error: ValueError) -> str:
    code = str(error) or "repository_parser_rejected"
    if not all(
        character.islower() or character.isdigit() or character == "_" for character in code
    ):
        return "repository_parser_rejected"
    return code[:80]


def _acquisition_error(error: RepositoryAcquisitionError) -> HTTPException:
    return HTTPException(503 if error.retryable else 422, detail={"code": error.code})


def _preview_response(
    parsed: ParsedRepositoryComponent, requested_revision: str
) -> RepositoryPreviewResponse:
    return RepositoryPreviewResponse(
        source_key=cast(Literal["seeed_wiki", "kicad_symbols"], parsed.source_key),
        repository_url=parsed.repository_url,
        requested_revision=requested_revision,
        revision=parsed.source_revision,
        file_path=parsed.source_file_path,
        entry_name=parsed.source_entry_name,
        original_url=parsed.original_url,
        parser_name=parsed.parser_name,
        parser_version=parsed.parser_version,
        parse_status=parsed.status.value,
        warnings=list(parsed.warnings),
        normalized_fields=dict(parsed.normalized_fields),
        provenance={
            key: [FieldProvenanceResponse(**item.as_dict()) for item in values]
            for key, values in parsed.provenance.items()
        },
        license=LicenseSnapshotResponse(
            name=parsed.license_snapshot.name,
            spdx=parsed.license_snapshot.spdx,
            url=parsed.license_snapshot.url,
            attribution=parsed.license_snapshot.attribution,
        ),
        modifications_notice=parsed.modifications_notice,
        draft_status="draft",
    )


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


@router.get("/repository/discovery", response_model=RepositoryDiscoveryResponse)
async def discover_repository_files(
    request: Request,
    response: Response,
    source_key: Annotated[Literal["seeed_wiki", "kicad_symbols"], Query()],
    revision: Annotated[str, Query(min_length=1, max_length=100)],
    actor: Annotated[Principal, Depends(editor)],
    session: Annotated[AsyncSession, Depends(database_session)],
    query: Annotated[str | None, Query(alias="q", min_length=2, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RepositoryDiscoveryResponse:
    del actor
    source = await ImportRepository(session).source_for_key(source_key)
    if source is None or source.repository_url is None:
        raise HTTPException(422, detail={"code": "source_disabled"})
    settings = cast(Settings, request.app.state.settings)
    try:
        result = await _acquirer(settings).discover_files(
            source.key,
            source.repository_url,
            revision,
            query=query,
            limit=limit,
        )
    except RepositoryAcquisitionError as error:
        raise _acquisition_error(error) from error
    response.headers["Cache-Control"] = "no-store"
    return RepositoryDiscoveryResponse(
        source_key=source_key,
        repository_url=result.repository_url,
        revision=result.revision,
        files_scanned=result.files_scanned,
        files=[
            RepositoryFileResponse(file_path=item.file_path, size=item.size)
            for item in result.files
        ],
    )


@router.get("/repository/entries", response_model=RepositoryEntryDiscoveryResponse)
async def discover_repository_entries(
    request: Request,
    response: Response,
    source_key: Annotated[Literal["seeed_wiki", "kicad_symbols"], Query()],
    revision: Annotated[str, Query(min_length=1, max_length=100)],
    file_path: Annotated[str, Query(min_length=1, max_length=1000)],
    actor: Annotated[Principal, Depends(editor)],
    session: Annotated[AsyncSession, Depends(database_session)],
    query: Annotated[str | None, Query(alias="q", min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RepositoryEntryDiscoveryResponse:
    del actor
    try:
        safe_path = normalize_repository_path(file_path)
    except ValueError as error:
        raise HTTPException(422, detail={"code": _safe_value_code(error)}) from error
    source = await ImportRepository(session).source_for_key(source_key)
    if source is None or source.repository_url is None:
        raise HTTPException(422, detail={"code": "source_disabled"})
    settings = cast(Settings, request.app.state.settings)
    try:
        _require_legacy_kicad_card_import(settings, source.key)
        acquired = await _acquirer(settings).acquire(
            source.key, source.repository_url, revision, safe_path
        )
        entries = await _adapter(settings, source.key).discover(
            acquired.snapshot, query=query, limit=limit
        )
    except RepositoryAcquisitionError as error:
        raise _acquisition_error(error) from error
    except ValueError as error:
        raise HTTPException(422, detail={"code": _safe_value_code(error)}) from error
    response.headers["Cache-Control"] = "no-store"
    return RepositoryEntryDiscoveryResponse(
        source_key=source_key,
        repository_url=source.repository_url,
        revision=acquired.snapshot.revision,
        entries=[
            RepositoryEntryResponse(
                file_path=entry.file_path,
                entry_name=entry.entry_name,
                title=entry.title,
            )
            for entry in entries
        ],
    )


@router.post("/repository/preview", response_model=RepositoryPreviewResponse)
async def preview_repository_import(
    payload: RepositoryImportRequest,
    request: Request,
    response: Response,
    actor: Annotated[Principal, Depends(editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> RepositoryPreviewResponse:
    del actor
    entry = _validated_entry(payload)
    source = await ImportRepository(session).source_for_key(payload.source_key)
    if source is None or source.repository_url is None:
        raise HTTPException(422, detail={"code": "source_disabled"})
    settings = cast(Settings, request.app.state.settings)
    try:
        _require_legacy_kicad_card_import(settings, source.key)
        acquired = await _acquirer(settings).acquire(
            source.key,
            source.repository_url,
            payload.revision,
            entry.file_path,
        )
        source_tag = payload.revision if payload.revision != acquired.snapshot.revision else None
        parsed = await _adapter(settings, source.key).parse_entry(
            acquired.snapshot,
            entry,
            parsed_at=datetime.now(UTC),
            source_tag=source_tag,
        )
    except RepositoryAcquisitionError as error:
        raise _acquisition_error(error) from error
    except ValueError as error:
        raise HTTPException(422, detail={"code": _safe_value_code(error)}) from error
    response.headers["Cache-Control"] = "no-store"
    return _preview_response(parsed, payload.revision)


@router.post("/repository", response_model=ImportJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_repository_import(
    payload: RepositoryImportRequest,
    request: Request,
    response: Response,
    actor: Annotated[Principal, Depends(editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
    queue: Annotated[ImportQueue, Depends(queue_from_request)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)],
) -> ImportJobResponse:
    entry = _validated_entry(payload)
    file_path = entry.file_path
    settings = cast(Settings, request.app.state.settings)
    try:
        _require_legacy_kicad_card_import(settings, payload.source_key)
    except ValueError as error:
        raise HTTPException(422, detail={"code": _safe_value_code(error)}) from error
    repository = ImportRepository(session)
    source = await repository.source_for_key(payload.source_key)
    if source is None:
        raise HTTPException(422, detail={"code": "source_disabled"})
    job = await repository.get_idempotent_job(actor.user_id, idempotency_key)
    if job is None:
        job = repository.add_repository_job(
            source,
            payload.revision,
            file_path,
            payload.entry_name,
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
    identity = (
        source.repository_url,
        payload.revision,
        file_path,
        payload.entry_name,
    )
    stored_identity = (
        job.repository_url,
        job.requested_revision,
        job.source_file_path,
        job.source_entry_name,
    )
    if stored_identity != identity:
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


@router.get("", response_model=ImportListResponse)
async def list_imports(
    request: Request,
    response: Response,
    actor: Annotated[Principal, Depends(import_viewer)],
    session: Annotated[AsyncSession, Depends(database_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ImportListResponse:
    filters = (
        ()
        if actor.can(Permission.SYSTEM_DIAGNOSTICS)
        else (ImportJob.requested_by == actor.user_id,)
    )
    total = int(
        await session.scalar(select(func.count()).select_from(ImportJob).where(*filters)) or 0
    )
    records = await session.execute(
        select(ImportJob, Source.display_name, User.display_name, Component.status)
        .join(Source, Source.id == ImportJob.source_id)
        .join(User, User.id == ImportJob.requested_by)
        .outerjoin(Component, Component.id == ImportJob.draft_component_id)
        .where(*filters)
        .order_by(ImportJob.created_at.desc(), ImportJob.id.desc())
        .limit(limit)
        .offset(offset)
    )
    now = datetime.now(UTC)
    settings = cast(Settings, request.app.state.settings)
    items = [
        _list_item(
            job,
            source_name,
            requested_by,
            component_status,
            can_retry=actor.can(Permission.IMPORTS_RETRY)
            and ImportRepository.is_manually_retryable(
                job,
                now,
                settings.import_lock_ttl_seconds,
            ),
            can_cancel=actor.can(Permission.IMPORTS_CANCEL)
            and job.status in {"queued", "running", "retrying"},
        )
        for job, source_name, requested_by, component_status in records.all()
    ]
    response.headers["Cache-Control"] = "no-store"
    return ImportListResponse(items=items, total=total, limit=limit, offset=offset)


async def _owned_job(
    job_id: UUID,
    actor: Principal,
    repository: ImportRepository,
) -> ImportJob:
    job = await repository.get_job(job_id, lock=True)
    if job is None or (
        not actor.can(Permission.SYSTEM_DIAGNOSTICS) and job.requested_by != actor.user_id
    ):
        raise HTTPException(404, detail={"code": "import_job_not_found"})
    return job


@router.post("/{job_id}/retry", response_model=ImportActionResponse)
async def retry_import(
    job_id: UUID,
    request: Request,
    actor: Annotated[Principal, Depends(import_retry)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
    queue: Annotated[ImportQueue, Depends(queue_from_request)],
) -> ImportActionResponse:
    repository = ImportRepository(session)
    job = await _owned_job(job_id, actor, repository)
    now = datetime.now(UTC)
    settings = cast(Settings, request.app.state.settings)
    try:
        reset = repository.prepare_manual_retry(job, now, settings.import_lock_ttl_seconds)
    except ValueError as error:
        raise HTTPException(409, detail={"code": "import_not_retryable"}) from error
    await AuthRepository(session).audit(
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
        await session.commit()
        raise HTTPException(503, detail={"code": "import_enqueue_failed"}) from error
    return ImportActionResponse(id=job.id, status="queued")


@router.post("/{job_id}/cancel", response_model=ImportActionResponse)
async def cancel_import(
    job_id: UUID,
    actor: Annotated[Principal, Depends(import_cancel)],
    _: Annotated[Principal, Depends(csrf_principal)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ImportActionResponse:
    repository = ImportRepository(session)
    job = await _owned_job(job_id, actor, repository)
    now = datetime.now(UTC)
    try:
        repository.cancel(job, now)
    except ValueError as error:
        raise HTTPException(409, detail={"code": "import_not_cancellable"}) from error
    await AuthRepository(session).audit(
        now=now,
        actor_user_id=actor.user_id,
        action="import.job_cancelled",
        object_type="import_job",
        object_id=job.id,
        request_id=current_request_id(),
        outcome="success",
        details=None,
    )
    await session.commit()
    return ImportActionResponse(id=job.id, status="cancelled")


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_import(
    job_id: UUID,
    response: Response,
    actor: Annotated[Principal, Depends(import_viewer)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> ImportJobResponse:
    job = await ImportRepository(session).get_job(job_id)
    if job is None or (
        not actor.can(Permission.SYSTEM_DIAGNOSTICS) and job.requested_by != actor.user_id
    ):
        raise HTTPException(404, detail={"code": "import_job_not_found"})
    response.headers["Cache-Control"] = "no-store"
    return _response(job)
