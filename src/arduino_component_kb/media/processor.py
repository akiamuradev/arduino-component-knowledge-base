"""Idempotent durable image job processor."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.media.domain import MediaValidationError, RetryableJobError
from arduino_component_kb.media.images import process_image
from arduino_component_kb.media.models import MediaVariant
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.storage import MediaStorage, MinioStorage


async def process_media_job(
    job_id: UUID,
    settings: Settings,
    storage: MediaStorage | None = None,
) -> None:
    """Process one job; validation failures are durable and never retried."""
    database = Database(settings)
    object_storage = storage or MinioStorage(settings)
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
                original = await object_storage.download(asset.bucket, asset.object_key)
                processed = process_image(original, asset.declared_mime)
            except MediaValidationError as error:
                now = datetime.now(UTC)
                async with session.begin():
                    await repository.reject_job(job, asset, error.code, now)
                    await audit.audit(
                        now=now,
                        actor_user_id=asset.owner_user_id,
                        action="media.processing_rejected",
                        object_type="media_asset",
                        object_id=asset.id,
                        request_id=None,
                        outcome="rejected",
                        details={"code": error.code},
                    )
                return
            except Exception as error:
                now = datetime.now(UTC)
                terminal = job.attempts >= job.max_attempts
                delay_seconds = min(60, 5 * (2 ** (job.attempts - 1)))
                async with session.begin():
                    await repository.record_storage_failure(
                        job,
                        asset,
                        terminal=terminal,
                        now=now,
                        retry_delay_seconds=delay_seconds,
                    )
                    if terminal:
                        await audit.audit(
                            now=now,
                            actor_user_id=asset.owner_user_id,
                            action="media.processing_failed",
                            object_type="media_asset",
                            object_id=asset.id,
                            request_id=None,
                            outcome="error",
                            details={"code": "media_storage_failed"},
                        )
                if not terminal:
                    raise RetryableJobError(delay_seconds * 1000) from error
                raise

            try:
                variants: list[MediaVariant] = []
                for variant in processed.variants:
                    object_key = f"images/{asset.id}/{variant.name}.webp"
                    await object_storage.upload(
                        settings.minio_variants_bucket,
                        object_key,
                        variant.data,
                        "image/webp",
                    )
                    variants.append(
                        MediaVariant(
                            id=uuid4(),
                            asset_id=asset.id,
                            variant=variant.name,
                            bucket=settings.minio_variants_bucket,
                            object_key=object_key,
                            mime="image/webp",
                            size_bytes=len(variant.data),
                            sha256=variant.sha256,
                            width=variant.width,
                            height=variant.height,
                        )
                    )
            except Exception as error:
                now = datetime.now(UTC)
                terminal = job.attempts >= job.max_attempts
                delay_seconds = min(60, 5 * (2 ** (job.attempts - 1)))
                async with session.begin():
                    await repository.record_storage_failure(
                        job,
                        asset,
                        terminal=terminal,
                        now=now,
                        retry_delay_seconds=delay_seconds,
                    )
                    if terminal:
                        await audit.audit(
                            now=now,
                            actor_user_id=asset.owner_user_id,
                            action="media.processing_failed",
                            object_type="media_asset",
                            object_id=asset.id,
                            request_id=None,
                            outcome="error",
                            details={"code": "media_storage_failed"},
                        )
                if not terminal:
                    raise RetryableJobError(delay_seconds * 1000) from error
                raise
            now = datetime.now(UTC)
            async with session.begin():
                await repository.complete_job(
                    job,
                    asset,
                    detected_mime=processed.detected_mime,
                    size_bytes=processed.size_bytes,
                    sha256=processed.sha256,
                    phash=processed.phash,
                    width=processed.width,
                    height=processed.height,
                    variants=variants,
                    now=now,
                )
                await audit.audit(
                    now=now,
                    actor_user_id=asset.owner_user_id,
                    action="media.processing_completed",
                    object_type="media_asset",
                    object_id=asset.id,
                    request_id=None,
                    outcome="success",
                )
    finally:
        await database.dispose()
