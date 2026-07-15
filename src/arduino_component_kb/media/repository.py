"""PostgreSQL repository for durable media metadata and job state."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.media.domain import MediaJobStatus, MediaStatus, UploadReservation
from arduino_component_kb.media.models import MediaAsset, MediaJob, MediaVariant


class MediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_pending(self, owner_id: UUID) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(MediaAsset)
            .where(
                MediaAsset.owner_user_id == owner_id,
                MediaAsset.status.in_((MediaStatus.PENDING.value, MediaStatus.PROCESSING.value)),
            )
        )
        return int(count or 0)

    async def create_reservation(
        self,
        *,
        asset_id: UUID,
        owner_id: UUID,
        kind: str,
        component_id: UUID | None,
        purpose: str,
        alt_text: str,
        attribution: str | None,
        bucket: str,
        object_key: str,
        declared_mime: str,
        declared_size_bytes: int,
        now: datetime,
        expires_at: datetime,
    ) -> UploadReservation:
        self.session.add(
            MediaAsset(
                id=asset_id,
                owner_user_id=owner_id,
                component_id=component_id,
                kind=kind,
                purpose=purpose,
                alt_text=alt_text,
                attribution=attribution,
                status=MediaStatus.PENDING.value,
                bucket=bucket,
                object_key=object_key,
                declared_mime=declared_mime,
                declared_size_bytes=declared_size_bytes,
                upload_expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
        )
        await self.session.flush()
        return UploadReservation(asset_id, bucket, object_key, declared_mime, expires_at)

    async def lock_asset(self, asset_id: UUID) -> MediaAsset | None:
        return cast(
            MediaAsset | None,
            await self.session.scalar(
                select(MediaAsset).where(MediaAsset.id == asset_id).with_for_update()
            ),
        )

    async def get_asset(self, asset_id: UUID) -> MediaAsset | None:
        return await self.session.get(MediaAsset, asset_id)

    async def variants(self, asset_id: UUID) -> tuple[MediaVariant, ...]:
        values = await self.session.scalars(
            select(MediaVariant)
            .where(MediaVariant.asset_id == asset_id)
            .order_by(MediaVariant.width)
        )
        return tuple(values)

    async def start_processing(
        self, asset: MediaAsset, now: datetime, max_attempts: int
    ) -> MediaJob:
        asset.status = MediaStatus.PROCESSING.value
        asset.updated_at = now
        job = MediaJob(
            id=uuid4(),
            asset_id=asset.id,
            status=MediaJobStatus.QUEUED.value,
            attempts=0,
            max_attempts=max_attempts,
            manual_retry_count=0,
            idempotency_key=f"media:{asset.id}",
            queue_name="videos" if asset.kind == "video" else "images",
            task_name="process_media_video" if asset.kind == "video" else "process_media_image",
            phase="queued",
            progress_percent=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def job_for_asset(self, asset_id: UUID) -> MediaJob | None:
        return cast(
            MediaJob | None,
            await self.session.scalar(select(MediaJob).where(MediaJob.asset_id == asset_id)),
        )

    async def lock_job(self, job_id: UUID) -> tuple[MediaJob, MediaAsset] | None:
        row = (
            await self.session.execute(
                select(MediaJob, MediaAsset)
                .join(MediaAsset, MediaAsset.id == MediaJob.asset_id)
                .where(MediaJob.id == job_id)
                .with_for_update(of=(MediaJob, MediaAsset))
            )
        ).one_or_none()
        if row is None:
            return None
        return row.tuple()

    async def list_jobs(
        self,
        *,
        status: str | None,
        kind: str | None,
        limit: int,
        offset: int,
    ) -> tuple[tuple[tuple[MediaJob, MediaAsset], ...], int]:
        filters = []
        if status is not None:
            filters.append(MediaJob.status == status)
        if kind is not None:
            filters.append(MediaAsset.kind == kind)
        total = await self.session.scalar(
            select(func.count())
            .select_from(MediaJob)
            .join(MediaAsset, MediaAsset.id == MediaJob.asset_id)
            .where(*filters)
        )
        rows = await self.session.execute(
            select(MediaJob, MediaAsset)
            .join(MediaAsset, MediaAsset.id == MediaJob.asset_id)
            .where(*filters)
            .order_by(MediaJob.updated_at.desc(), MediaJob.id)
            .limit(limit)
            .offset(offset)
        )
        return tuple(row.tuple() for row in rows), int(total or 0)

    async def mark_enqueued(self, job_id: UUID, now: datetime) -> None:
        job = await self.session.get(MediaJob, job_id)
        if job is not None:
            job.last_enqueued_at = now
            job.updated_at = now

    async def update_job_progress(
        self, job: MediaJob, *, phase: str, progress_percent: int, now: datetime
    ) -> None:
        job.phase = phase
        job.progress_percent = max(job.progress_percent, progress_percent)
        job.heartbeat_at = now
        job.updated_at = now

    async def claim_job(
        self, job_id: UUID, now: datetime, lease_seconds: int
    ) -> tuple[MediaJob, MediaAsset] | None:
        row = (
            await self.session.execute(
                select(MediaJob, MediaAsset)
                .join(MediaAsset, MediaAsset.id == MediaJob.asset_id)
                .where(MediaJob.id == job_id)
                .with_for_update(of=(MediaJob, MediaAsset))
            )
        ).one_or_none()
        if row is None:
            return None
        job, asset = row.tuple()
        if job.status in {MediaJobStatus.SUCCEEDED.value, MediaJobStatus.FAILED.value}:
            return None
        if (
            job.status == MediaJobStatus.RETRYING.value
            and job.next_retry_at is not None
            and job.next_retry_at > now
        ):
            return None
        lease_reference = job.heartbeat_at or job.started_at
        if (
            job.status == MediaJobStatus.RUNNING.value
            and lease_reference is not None
            and lease_reference > now - timedelta(seconds=lease_seconds)
        ):
            return None
        if job.attempts >= job.max_attempts:
            job.status = MediaJobStatus.FAILED.value
            job.phase = "failed"
            job.error_code = "media_attempts_exhausted"
            job.finished_at = now
            job.updated_at = now
            asset.status = MediaStatus.REJECTED.value
            asset.failure_code = "media_attempts_exhausted"
            asset.updated_at = now
            return None
        job.status = MediaJobStatus.RUNNING.value
        job.attempts += 1
        job.phase = "starting"
        job.progress_percent = max(job.progress_percent, 1)
        job.started_at = now
        job.heartbeat_at = now
        job.next_retry_at = None
        job.updated_at = now
        return job, asset

    async def prepare_manual_retry(self, job: MediaJob, asset: MediaAsset, now: datetime) -> bool:
        if job.status == MediaJobStatus.QUEUED.value:
            return False
        if job.status != MediaJobStatus.FAILED.value:
            raise ValueError("job is not retryable")
        job.status = MediaJobStatus.QUEUED.value
        job.phase = "queued"
        job.progress_percent = 0
        job.attempts = 0
        job.manual_retry_count += 1
        job.error_code = None
        job.started_at = None
        job.finished_at = None
        job.heartbeat_at = None
        job.next_retry_at = None
        job.updated_at = now
        asset.status = MediaStatus.PROCESSING.value
        asset.failure_code = None
        asset.updated_at = now
        return True

    async def complete_job(
        self,
        job: MediaJob,
        asset: MediaAsset,
        *,
        detected_mime: str,
        size_bytes: int,
        sha256: str,
        phash: str,
        width: int,
        height: int,
        variants: list[MediaVariant],
        now: datetime,
    ) -> None:
        self.session.add_all(variants)
        asset.status = MediaStatus.READY.value
        asset.detected_mime = detected_mime
        asset.size_bytes = size_bytes
        asset.sha256 = sha256
        asset.phash = phash
        asset.width = width
        asset.height = height
        asset.failure_code = None
        asset.updated_at = now
        job.status = MediaJobStatus.SUCCEEDED.value
        job.phase = "completed"
        job.progress_percent = 100
        job.finished_at = now
        job.heartbeat_at = now
        job.next_retry_at = None
        job.updated_at = now
        job.error_code = None

    async def complete_video_job(
        self,
        job: MediaJob,
        asset: MediaAsset,
        *,
        detected_mime: str,
        size_bytes: int,
        sha256: str,
        width: int,
        height: int,
        duration_ms: int,
        video_codec: str,
        audio_codec: str | None,
        frame_rate: float,
        variants: list[MediaVariant],
        now: datetime,
    ) -> None:
        self.session.add_all(variants)
        asset.status = MediaStatus.READY.value
        asset.detected_mime = detected_mime
        asset.size_bytes = size_bytes
        asset.sha256 = sha256
        asset.width = width
        asset.height = height
        asset.duration_ms = duration_ms
        asset.video_codec = video_codec
        asset.audio_codec = audio_codec
        asset.frame_rate = frame_rate
        asset.failure_code = None
        asset.updated_at = now
        job.status = MediaJobStatus.SUCCEEDED.value
        job.phase = "completed"
        job.progress_percent = 100
        job.finished_at = now
        job.heartbeat_at = now
        job.next_retry_at = None
        job.updated_at = now
        job.error_code = None

    async def reject_job(self, job: MediaJob, asset: MediaAsset, code: str, now: datetime) -> None:
        asset.status = MediaStatus.REJECTED.value
        asset.failure_code = code
        asset.updated_at = now
        job.status = MediaJobStatus.FAILED.value
        job.phase = "failed"
        job.error_code = code
        job.finished_at = now
        job.heartbeat_at = now
        job.next_retry_at = None
        job.updated_at = now

    async def record_storage_failure(
        self,
        job: MediaJob,
        asset: MediaAsset,
        *,
        terminal: bool,
        now: datetime,
        transient_code: str = "media_storage_transient",
        terminal_code: str = "media_storage_failed",
        retry_delay_seconds: int = 5,
    ) -> None:
        job.status = MediaJobStatus.FAILED.value if terminal else MediaJobStatus.RETRYING.value
        job.phase = "retrying" if not terminal else "failed"
        job.error_code = transient_code
        job.updated_at = now
        job.heartbeat_at = now
        job.next_retry_at = None if terminal else now + timedelta(seconds=retry_delay_seconds)
        if terminal:
            asset.status = MediaStatus.REJECTED.value
            asset.failure_code = terminal_code
            asset.updated_at = now
            job.error_code = terminal_code
            job.finished_at = now
