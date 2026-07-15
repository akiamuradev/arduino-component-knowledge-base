"""Durable Dramatiq video job processor."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.media.domain import (
    MAX_VIDEO_BYTES,
    MediaValidationError,
    RetryableJobError,
)
from arduino_component_kb.media.models import MediaAsset, MediaJob, MediaVariant
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.storage import MediaStorage, MinioStorage
from arduino_component_kb.media.videos import MediaToolError, ProcessedVideo, VideoProcessor


async def process_video_job(
    job_id: UUID,
    settings: Settings,
    storage: MediaStorage | None = None,
    video_processor: VideoProcessor | None = None,
) -> None:
    database = Database(settings)
    object_storage = storage or MinioStorage(settings)
    processor = video_processor or VideoProcessor(settings)
    try:
        async with database.sessions() as session:
            repository = MediaRepository(session)
            audit = AuthRepository(session)
            async with session.begin():
                claimed = await repository.claim_job(
                    job_id, datetime.now(UTC), settings.media_job_lease_seconds
                )
            if claimed is None:
                return
            job, asset = claimed
            try:
                with TemporaryDirectory(prefix="ackb-video-") as directory:
                    root = Path(directory)
                    original = root / "original"
                    rendition = root / "rendition.mp4"
                    poster = root / "poster.webp"
                    await _progress(repository, session, job, "downloading", 5)
                    try:
                        await object_storage.download_to_file(
                            asset.bucket, asset.object_key, original, MAX_VIDEO_BYTES
                        )
                    except ValueError:
                        raise MediaValidationError("video_size_not_allowed") from None
                    await _progress(repository, session, job, "probing", 10)
                    await processor.probe(original, asset.declared_mime)
                    await _progress(repository, session, job, "transcoding", 25)
                    processed = await processor.transcode(
                        original, rendition, poster, asset.declared_mime
                    )
                    await _progress(repository, session, job, "uploading", 90)
                    rendition_key = f"videos/{asset.id}/video_720p.mp4"
                    poster_key = f"videos/{asset.id}/poster.webp"
                    await object_storage.upload_file(
                        settings.minio_variants_bucket,
                        rendition_key,
                        processed.rendition.path,
                        processed.rendition.mime,
                    )
                    await object_storage.upload_file(
                        settings.minio_variants_bucket,
                        poster_key,
                        processed.poster.path,
                        processed.poster.mime,
                    )
                    variants = _variants(
                        asset,
                        settings.minio_variants_bucket,
                        rendition_key,
                        poster_key,
                        processed,
                    )
                    now = datetime.now(UTC)
                    async with session.begin():
                        await repository.complete_video_job(
                            job,
                            asset,
                            detected_mime=processed.original.detected_mime,
                            size_bytes=processed.original_size_bytes,
                            sha256=processed.original_sha256,
                            width=processed.original.width,
                            height=processed.original.height,
                            duration_ms=processed.original.duration_ms,
                            video_codec=processed.original.video_codec,
                            audio_codec=processed.original.audio_codec,
                            frame_rate=processed.original.frame_rate,
                            variants=variants,
                            now=now,
                        )
                        await audit.audit(
                            now=now,
                            actor_user_id=asset.owner_user_id,
                            action="media.video_processing_completed",
                            object_type="media_asset",
                            object_id=asset.id,
                            request_id=None,
                            outcome="success",
                        )
            except MediaValidationError as error:
                await _reject(repository, audit, session, job, asset, error.code)
            except MediaToolError as error:
                await _transient_failure(repository, audit, session, job, asset)
                if job.status != "failed":
                    raise RetryableJobError(_retry_delay_seconds(job) * 1000) from error
                raise
            except Exception as error:
                await _transient_failure(repository, audit, session, job, asset)
                if job.status != "failed":
                    raise RetryableJobError(_retry_delay_seconds(job) * 1000) from error
                raise
    finally:
        await database.dispose()


async def _progress(
    repository: MediaRepository, session: AsyncSession, job: MediaJob, phase: str, percent: int
) -> None:
    async with session.begin():
        await repository.update_job_progress(
            job, phase=phase, progress_percent=percent, now=datetime.now(UTC)
        )


async def _reject(
    repository: MediaRepository,
    audit: AuthRepository,
    session: AsyncSession,
    job: MediaJob,
    asset: MediaAsset,
    code: str,
) -> None:
    now = datetime.now(UTC)
    async with session.begin():
        await repository.reject_job(job, asset, code, now)
        await audit.audit(
            now=now,
            actor_user_id=asset.owner_user_id,
            action="media.video_processing_rejected",
            object_type="media_asset",
            object_id=asset.id,
            request_id=None,
            outcome="rejected",
            details={"code": code},
        )


async def _transient_failure(
    repository: MediaRepository,
    audit: AuthRepository,
    session: AsyncSession,
    job: MediaJob,
    asset: MediaAsset,
) -> None:
    now = datetime.now(UTC)
    terminal = job.attempts >= job.max_attempts
    delay_seconds = _retry_delay_seconds(job)
    async with session.begin():
        await repository.record_storage_failure(
            job,
            asset,
            terminal=terminal,
            now=now,
            transient_code="media_processing_transient",
            terminal_code="media_processing_failed",
            retry_delay_seconds=delay_seconds,
        )
        if terminal:
            await audit.audit(
                now=now,
                actor_user_id=asset.owner_user_id,
                action="media.video_processing_failed",
                object_type="media_asset",
                object_id=asset.id,
                request_id=None,
                outcome="error",
                details={"code": "media_processing_failed"},
            )


def _retry_delay_seconds(job: MediaJob) -> int:
    return int(min(120, 15 * (2 ** (int(job.attempts) - 1))))


def _variants(
    asset: MediaAsset,
    bucket: str,
    rendition_key: str,
    poster_key: str,
    processed: ProcessedVideo,
) -> list[MediaVariant]:
    return [
        MediaVariant(
            id=uuid4(),
            asset_id=asset.id,
            variant="video_720p",
            bucket=bucket,
            object_key=rendition_key,
            mime=processed.rendition.mime,
            size_bytes=processed.rendition.size_bytes,
            sha256=processed.rendition.sha256,
            width=processed.rendition.width,
            height=processed.rendition.height,
            duration_ms=processed.rendition.duration_ms,
            video_codec=processed.rendition.video_codec,
            audio_codec=processed.rendition.audio_codec,
            frame_rate=processed.rendition.frame_rate,
        ),
        MediaVariant(
            id=uuid4(),
            asset_id=asset.id,
            variant="poster",
            bucket=bucket,
            object_key=poster_key,
            mime=processed.poster.mime,
            size_bytes=processed.poster.size_bytes,
            sha256=processed.poster.sha256,
            width=processed.poster.width,
            height=processed.poster.height,
        ),
    ]
