"""Dependency-isolated smoke test for durable background job transitions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.media.domain import MediaJobStatus, MediaStatus
from arduino_component_kb.media.models import MediaAsset, MediaJob
from arduino_component_kb.media.repository import MediaRepository


async def smoke() -> None:
    now = datetime.now(UTC)
    asset_id = uuid4()
    asset = MediaAsset(
        id=asset_id,
        owner_user_id=uuid4(),
        kind="image",
        purpose="gallery",
        alt_text="Smoke test board",
        status=MediaStatus.PROCESSING.value,
        bucket="media-quarantine",
        object_key=f"quarantine/{asset_id}/original",
        declared_mime="image/png",
        declared_size_bytes=100,
        upload_expires_at=now + timedelta(minutes=10),
        created_at=now,
        updated_at=now,
    )
    job = MediaJob(
        id=uuid4(),
        asset_id=asset_id,
        status=MediaJobStatus.RUNNING.value,
        attempts=1,
        max_attempts=4,
        manual_retry_count=0,
        idempotency_key=f"media:{asset_id}",
        queue_name="images",
        task_name="process_media_image",
        phase="downloading",
        progress_percent=10,
        created_at=now,
        updated_at=now,
    )
    repository = MediaRepository(Mock(spec=AsyncSession))
    await repository.record_storage_failure(
        job, asset, terminal=False, now=now, retry_delay_seconds=5
    )
    assert job.status == MediaJobStatus.RETRYING.value
    job.status = MediaJobStatus.FAILED.value
    await repository.prepare_manual_retry(job, asset, now + timedelta(seconds=5))
    assert job.status == MediaJobStatus.QUEUED.value
    assert job.manual_retry_count == 1


def main() -> int:
    asyncio.run(smoke())
    print("Durable background jobs smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
