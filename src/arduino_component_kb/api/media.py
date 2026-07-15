"""Authorized image upload reservation and processing status API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import (
    csrf_principal,
    database_session,
    require_roles,
)
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.logging import current_request_id
from arduino_component_kb.media.domain import (
    MAX_IMAGE_BYTES,
    MAX_VIDEO_BYTES,
    MediaKind,
    MediaNotFoundError,
    MediaQuotaError,
    MediaStateConflictError,
    MediaValidationError,
)
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.service import MediaQueue, MediaService
from arduino_component_kb.media.storage import MediaStorage

router = APIRouter(prefix="/api/v1/media", tags=["media"])
media_editor = require_roles(Role.TEACHER, Role.ADMINISTRATOR)


class UploadReservationRequest(BaseModel):
    component_id: UUID | None = None
    purpose: str = Field(min_length=1, max_length=40)
    alt_text: str = Field(min_length=1, max_length=500)
    attribution: str | None = Field(default=None, max_length=1000)
    declared_mime: str
    declared_size_bytes: int = Field(gt=0, le=MAX_IMAGE_BYTES)


class VideoUploadReservationRequest(BaseModel):
    component_id: UUID | None = None
    purpose: str = Field(min_length=1, max_length=40)
    alt_text: str = Field(min_length=1, max_length=500)
    attribution: str | None = Field(default=None, max_length=1000)
    declared_mime: str
    declared_size_bytes: int = Field(gt=0, le=MAX_VIDEO_BYTES)


class UploadReservationResponse(BaseModel):
    asset_id: UUID
    upload_url: str
    upload_headers: dict[str, str]
    expires_at: datetime


class UploadConfirmationResponse(BaseModel):
    asset_id: UUID
    job_id: UUID
    status: str


class VariantResponse(BaseModel):
    name: str
    mime: str
    width: int
    height: int
    size_bytes: int
    sha256: str
    duration_ms: int | None
    video_codec: str | None
    audio_codec: str | None
    frame_rate: float | None


class MediaAssetResponse(BaseModel):
    id: UUID
    kind: str
    component_id: UUID | None
    purpose: str
    alt_text: str
    status: str
    declared_mime: str
    detected_mime: str | None
    size_bytes: int | None
    sha256: str | None
    phash: str | None
    width: int | None
    height: int | None
    duration_ms: int | None
    video_codec: str | None
    audio_codec: str | None
    frame_rate: float | None
    failure_code: str | None
    job_status: str | None
    phase: str | None
    progress_percent: int | None
    variants: list[VariantResponse]


def media_service_from_request(
    request: Request,
    session: Annotated[AsyncSession, Depends(database_session)],
) -> MediaService:
    return MediaService(
        MediaRepository(session),
        AuthRepository(session),
        cast(MediaStorage, request.app.state.media_storage),
        cast(Settings, request.app.state.settings),
    )


def media_queue_from_request(request: Request) -> MediaQueue:
    return cast(MediaQueue, request.app.state.media_queue)


@router.post("/images/uploads", response_model=UploadReservationResponse, status_code=201)
async def reserve_upload(
    payload: UploadReservationRequest,
    response: Response,
    actor: Annotated[Principal, Depends(media_editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[MediaService, Depends(media_service_from_request)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> UploadReservationResponse:
    try:
        result = await service.reserve_upload(
            actor=actor,
            kind=MediaKind.IMAGE,
            component_id=payload.component_id,
            purpose=payload.purpose,
            alt_text=payload.alt_text,
            attribution=payload.attribution,
            declared_mime=payload.declared_mime,
            declared_size_bytes=payload.declared_size_bytes,
            request_id=current_request_id(),
        )
    except MediaQuotaError as error:
        raise HTTPException(429, detail={"code": "media_pending_quota_exceeded"}) from error
    except MediaValidationError as error:
        raise HTTPException(422, detail={"code": error.code}) from error
    await session.commit()
    response.headers["Cache-Control"] = "no-store"
    return UploadReservationResponse(
        asset_id=result.reservation.asset_id,
        upload_url=result.url,
        upload_headers={"Content-Type": result.reservation.declared_mime},
        expires_at=result.reservation.expires_at,
    )


@router.post("/images/{asset_id}/complete", response_model=UploadConfirmationResponse)
async def confirm_upload(
    asset_id: UUID,
    response: Response,
    actor: Annotated[Principal, Depends(media_editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[MediaService, Depends(media_service_from_request)],
    session: Annotated[AsyncSession, Depends(database_session)],
    queue: Annotated[MediaQueue, Depends(media_queue_from_request)],
) -> UploadConfirmationResponse:
    error: Exception | None = None
    job_id: UUID | None = None
    try:
        asset = await service.visible_asset(actor, asset_id, MediaKind.IMAGE)
        job_id = await service.confirm_upload(
            actor=actor, asset_id=asset.id, request_id=current_request_id()
        )
    except (MediaNotFoundError, MediaStateConflictError, MediaValidationError) as caught:
        error = caught
    await session.commit()
    if isinstance(error, MediaNotFoundError):
        raise HTTPException(404, detail={"code": "media_not_found"})
    if isinstance(error, MediaStateConflictError):
        raise HTTPException(409, detail={"code": "media_state_conflict"})
    if isinstance(error, MediaValidationError):
        raise HTTPException(422, detail={"code": error.code})
    if job_id is None:
        raise HTTPException(500, detail={"code": "media_job_missing"})
    try:
        queue.enqueue(job_id, MediaKind.IMAGE)
    except Exception as error:
        raise HTTPException(503, detail={"code": "media_enqueue_failed"}) from error
    await service.repository.mark_enqueued(job_id, datetime.now(UTC))
    await session.commit()
    response.headers["Cache-Control"] = "no-store"
    return UploadConfirmationResponse(asset_id=asset_id, job_id=job_id, status="queued")


@router.get("/images/{asset_id}", response_model=MediaAssetResponse)
async def asset_status(
    asset_id: UUID,
    response: Response,
    actor: Annotated[Principal, Depends(media_editor)],
    service: Annotated[MediaService, Depends(media_service_from_request)],
) -> MediaAssetResponse:
    try:
        asset = await service.visible_asset(actor, asset_id, MediaKind.IMAGE)
    except MediaNotFoundError as error:
        raise HTTPException(404, detail={"code": "media_not_found"}) from error
    variants = await service.repository.variants(asset.id)
    job = await service.repository.job_for_asset(asset.id)
    response.headers["Cache-Control"] = "no-store"
    return MediaAssetResponse(
        id=asset.id,
        kind=asset.kind,
        component_id=asset.component_id,
        purpose=asset.purpose,
        alt_text=asset.alt_text,
        status=asset.status,
        declared_mime=asset.declared_mime,
        detected_mime=asset.detected_mime,
        size_bytes=asset.size_bytes,
        sha256=asset.sha256,
        phash=asset.phash,
        width=asset.width,
        height=asset.height,
        duration_ms=asset.duration_ms,
        video_codec=asset.video_codec,
        audio_codec=asset.audio_codec,
        frame_rate=asset.frame_rate,
        failure_code=asset.failure_code,
        job_status=job.status if job else None,
        phase=job.phase if job else None,
        progress_percent=job.progress_percent if job else None,
        variants=[
            VariantResponse(
                name=variant.variant,
                mime=variant.mime,
                width=variant.width,
                height=variant.height,
                size_bytes=variant.size_bytes,
                sha256=variant.sha256,
                duration_ms=variant.duration_ms,
                video_codec=variant.video_codec,
                audio_codec=variant.audio_codec,
                frame_rate=variant.frame_rate,
            )
            for variant in variants
        ],
    )


@router.post("/videos/uploads", response_model=UploadReservationResponse, status_code=201)
async def reserve_video_upload(
    payload: VideoUploadReservationRequest,
    response: Response,
    actor: Annotated[Principal, Depends(media_editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[MediaService, Depends(media_service_from_request)],
    session: Annotated[AsyncSession, Depends(database_session)],
) -> UploadReservationResponse:
    try:
        result = await service.reserve_upload(
            actor=actor,
            kind=MediaKind.VIDEO,
            component_id=payload.component_id,
            purpose=payload.purpose,
            alt_text=payload.alt_text,
            attribution=payload.attribution,
            declared_mime=payload.declared_mime,
            declared_size_bytes=payload.declared_size_bytes,
            request_id=current_request_id(),
        )
    except MediaQuotaError as error:
        raise HTTPException(429, detail={"code": "media_pending_quota_exceeded"}) from error
    except MediaValidationError as error:
        raise HTTPException(422, detail={"code": error.code}) from error
    await session.commit()
    response.headers["Cache-Control"] = "no-store"
    return UploadReservationResponse(
        asset_id=result.reservation.asset_id,
        upload_url=result.url,
        upload_headers={"Content-Type": result.reservation.declared_mime},
        expires_at=result.reservation.expires_at,
    )


@router.post("/videos/{asset_id}/complete", response_model=UploadConfirmationResponse)
async def confirm_video_upload(
    asset_id: UUID,
    response: Response,
    actor: Annotated[Principal, Depends(media_editor)],
    _: Annotated[Principal, Depends(csrf_principal)],
    service: Annotated[MediaService, Depends(media_service_from_request)],
    session: Annotated[AsyncSession, Depends(database_session)],
    queue: Annotated[MediaQueue, Depends(media_queue_from_request)],
) -> UploadConfirmationResponse:
    error: Exception | None = None
    job_id: UUID | None = None
    try:
        asset = await service.visible_asset(actor, asset_id, MediaKind.VIDEO)
        job_id = await service.confirm_upload(
            actor=actor, asset_id=asset.id, request_id=current_request_id()
        )
    except (MediaNotFoundError, MediaStateConflictError, MediaValidationError) as caught:
        error = caught
    await session.commit()
    if isinstance(error, MediaNotFoundError):
        raise HTTPException(404, detail={"code": "media_not_found"})
    if isinstance(error, MediaStateConflictError):
        raise HTTPException(409, detail={"code": "media_state_conflict"})
    if isinstance(error, MediaValidationError):
        raise HTTPException(422, detail={"code": error.code})
    if job_id is None:
        raise HTTPException(500, detail={"code": "media_job_missing"})
    try:
        queue.enqueue(job_id, MediaKind.VIDEO)
    except Exception as queue_error:
        raise HTTPException(503, detail={"code": "media_enqueue_failed"}) from queue_error
    await service.repository.mark_enqueued(job_id, datetime.now(UTC))
    await session.commit()
    response.headers["Cache-Control"] = "no-store"
    return UploadConfirmationResponse(asset_id=asset_id, job_id=job_id, status="queued")


@router.get("/videos/{asset_id}", response_model=MediaAssetResponse)
async def video_asset_status(
    asset_id: UUID,
    response: Response,
    actor: Annotated[Principal, Depends(media_editor)],
    service: Annotated[MediaService, Depends(media_service_from_request)],
) -> MediaAssetResponse:
    try:
        asset = await service.visible_asset(actor, asset_id, MediaKind.VIDEO)
    except MediaNotFoundError as error:
        raise HTTPException(404, detail={"code": "media_not_found"}) from error
    variants = await service.repository.variants(asset.id)
    job = await service.repository.job_for_asset(asset.id)
    response.headers["Cache-Control"] = "no-store"
    return MediaAssetResponse(
        id=asset.id,
        kind=asset.kind,
        component_id=asset.component_id,
        purpose=asset.purpose,
        alt_text=asset.alt_text,
        status=asset.status,
        declared_mime=asset.declared_mime,
        detected_mime=asset.detected_mime,
        size_bytes=asset.size_bytes,
        sha256=asset.sha256,
        phash=asset.phash,
        width=asset.width,
        height=asset.height,
        duration_ms=asset.duration_ms,
        video_codec=asset.video_codec,
        audio_codec=asset.audio_codec,
        frame_rate=asset.frame_rate,
        failure_code=asset.failure_code,
        job_status=job.status if job else None,
        phase=job.phase if job else None,
        progress_percent=job.progress_percent if job else None,
        variants=[
            VariantResponse(
                name=variant.variant,
                mime=variant.mime,
                width=variant.width,
                height=variant.height,
                size_bytes=variant.size_bytes,
                sha256=variant.sha256,
                duration_ms=variant.duration_ms,
                video_codec=variant.video_codec,
                audio_codec=variant.audio_codec,
                frame_rate=variant.frame_rate,
            )
            for variant in variants
        ],
    )
