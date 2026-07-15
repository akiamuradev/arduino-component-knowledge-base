"""Media upload reservation, confirmation, and authorization policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.media.domain import (
    ALLOWED_IMAGE_MIMES,
    ALLOWED_VIDEO_MIMES,
    MAX_IMAGE_BYTES,
    MAX_VIDEO_BYTES,
    MediaKind,
    MediaNotFoundError,
    MediaQuotaError,
    MediaStateConflictError,
    MediaStatus,
    MediaValidationError,
    UploadReservation,
)
from arduino_component_kb.media.models import MediaAsset
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.storage import MediaStorage


class MediaQueue(Protocol):
    def enqueue(self, job_id: UUID, kind: MediaKind) -> None: ...


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    reservation: UploadReservation
    url: str


class MediaService:
    def __init__(
        self,
        repository: MediaRepository,
        audit: AuthRepository,
        storage: MediaStorage,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.audit = audit
        self.storage = storage
        self.settings = settings

    async def reserve_upload(
        self,
        *,
        actor: Principal,
        kind: MediaKind,
        component_id: UUID | None,
        purpose: str,
        alt_text: str,
        attribution: str | None,
        declared_mime: str,
        declared_size_bytes: int,
        request_id: str | None,
    ) -> PresignedUpload:
        allowed_mimes = ALLOWED_IMAGE_MIMES if kind is MediaKind.IMAGE else ALLOWED_VIDEO_MIMES
        max_bytes = MAX_IMAGE_BYTES if kind is MediaKind.IMAGE else MAX_VIDEO_BYTES
        if declared_mime not in allowed_mimes:
            raise MediaValidationError(f"{kind.value}_declared_mime_not_allowed")
        if not 0 < declared_size_bytes <= max_bytes:
            raise MediaValidationError(f"{kind.value}_size_not_allowed")
        if (
            await self.repository.count_pending(actor.user_id)
            >= self.settings.media_pending_upload_limit
        ):
            raise MediaQuotaError
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.settings.media_presign_ttl_seconds)
        asset_id = uuid4()
        object_key = f"{kind.value}s/{actor.user_id}/{asset_id}/original"
        reservation = await self.repository.create_reservation(
            asset_id=asset_id,
            owner_id=actor.user_id,
            kind=kind.value,
            component_id=component_id,
            purpose=purpose,
            alt_text=alt_text.strip(),
            attribution=attribution.strip() if attribution else None,
            bucket=self.settings.minio_quarantine_bucket,
            object_key=object_key,
            declared_mime=declared_mime,
            declared_size_bytes=declared_size_bytes,
            now=now,
            expires_at=expires_at,
        )
        url = await self.storage.presigned_put(
            reservation.bucket,
            reservation.object_key,
            self.settings.media_presign_ttl_seconds,
        )
        await self.audit.audit(
            now=now,
            actor_user_id=actor.user_id,
            action="media.upload_reserved",
            object_type="media_asset",
            object_id=asset_id,
            request_id=request_id,
            outcome="success",
        )
        return PresignedUpload(reservation, url)

    async def confirm_upload(
        self, *, actor: Principal, asset_id: UUID, request_id: str | None
    ) -> UUID:
        now = datetime.now(UTC)
        asset = await self.repository.lock_asset(asset_id)
        self._authorize_owner(actor, asset)
        if asset is None:
            raise MediaNotFoundError
        if asset.status == MediaStatus.PROCESSING.value:
            existing_job = await self.repository.job_for_asset(asset.id)
            if existing_job is None:
                raise MediaStateConflictError
            return existing_job.id
        if asset.status != MediaStatus.PENDING.value:
            raise MediaStateConflictError
        if asset.upload_expires_at <= now:
            await self._reject_pending(asset, "upload_expired", actor, request_id, now)
            raise MediaValidationError("upload_expired")
        metadata = await self.storage.stat(asset.bucket, asset.object_key)
        max_bytes = MAX_IMAGE_BYTES if asset.kind == MediaKind.IMAGE.value else MAX_VIDEO_BYTES
        if metadata.size != asset.declared_size_bytes or not 0 < metadata.size <= max_bytes:
            await self._reject_pending(asset, "uploaded_size_mismatch", actor, request_id, now)
            raise MediaValidationError("uploaded_size_mismatch")
        job = await self.repository.start_processing(
            asset, now, self.settings.media_job_max_attempts
        )
        await self.audit.audit(
            now=now,
            actor_user_id=actor.user_id,
            action="media.upload_confirmed",
            object_type="media_asset",
            object_id=asset.id,
            request_id=request_id,
            outcome="success",
        )
        return job.id

    async def visible_asset(
        self, actor: Principal, asset_id: UUID, expected_kind: MediaKind | None = None
    ) -> MediaAsset:
        asset = await self.repository.get_asset(asset_id)
        self._authorize_owner(actor, asset)
        if asset is None or (expected_kind is not None and asset.kind != expected_kind.value):
            raise MediaNotFoundError
        return asset

    @staticmethod
    def _authorize_owner(actor: Principal, asset: MediaAsset | None) -> None:
        if asset is None or (
            asset.owner_user_id != actor.user_id and Role.ADMINISTRATOR not in actor.roles
        ):
            raise MediaNotFoundError

    async def _reject_pending(
        self,
        asset: MediaAsset,
        code: str,
        actor: Principal,
        request_id: str | None,
        now: datetime,
    ) -> None:
        asset.status = MediaStatus.REJECTED.value
        asset.failure_code = code
        asset.updated_at = now
        await self.audit.audit(
            now=now,
            actor_user_id=actor.user_id,
            action="media.upload_rejected",
            object_type="media_asset",
            object_id=asset.id,
            request_id=request_id,
            outcome="rejected",
            details={"code": code},
        )
