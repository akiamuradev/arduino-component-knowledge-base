"""Durable background job state and retry tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.media.domain import MediaJobStatus, MediaStatus
from arduino_component_kb.media.models import MediaAsset, MediaJob
from arduino_component_kb.media.repository import MediaRepository


class FakeRow:
    def __init__(self, job: MediaJob, asset: MediaAsset) -> None:
        self.job = job
        self.asset = asset

    def tuple(self) -> tuple[MediaJob, MediaAsset]:
        return self.job, self.asset


class FakeResult:
    def __init__(self, job: MediaJob, asset: MediaAsset) -> None:
        self.row = FakeRow(job, asset)

    def one_or_none(self) -> FakeRow:
        return self.row


def repository_with_claim(job: MediaJob, asset: MediaAsset) -> MediaRepository:
    session = cast(
        AsyncSession,
        SimpleNamespace(execute=AsyncMock(return_value=FakeResult(job, asset))),
    )
    return MediaRepository(session)


def job_pair(status: str = MediaJobStatus.RUNNING.value) -> tuple[MediaJob, MediaAsset]:
    now = datetime.now(UTC)
    asset_id = uuid4()
    asset = MediaAsset(
        id=asset_id,
        owner_user_id=uuid4(),
        kind="image",
        purpose="gallery",
        alt_text="Board",
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
        status=status,
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
    return job, asset


async def test_transient_failure_is_durable_until_retry() -> None:
    job, asset = job_pair()
    now = datetime.now(UTC)
    repository = MediaRepository(Mock(spec=AsyncSession))

    await repository.record_storage_failure(
        job, asset, terminal=False, now=now, retry_delay_seconds=15
    )

    assert job.status == MediaJobStatus.RETRYING.value
    assert job.phase == "retrying"
    assert job.error_code == "media_storage_transient"
    assert job.next_retry_at == now + timedelta(seconds=15)
    assert asset.status == MediaStatus.PROCESSING.value


async def test_terminal_failure_can_be_reset_once_by_admin() -> None:
    job, asset = job_pair(MediaJobStatus.FAILED.value)
    job.phase = "failed"
    job.error_code = "media_storage_failed"
    job.finished_at = datetime.now(UTC)
    asset.status = MediaStatus.REJECTED.value
    asset.failure_code = "media_storage_failed"
    now = datetime.now(UTC)
    repository = MediaRepository(Mock(spec=AsyncSession))

    reset = await repository.prepare_manual_retry(job, asset, now)

    assert reset is True
    assert job.status == MediaJobStatus.QUEUED.value
    assert job.attempts == 0
    assert job.manual_retry_count == 1
    assert job.error_code is None
    assert asset.status == MediaStatus.PROCESSING.value
    assert asset.failure_code is None
    assert await repository.prepare_manual_retry(job, asset, now) is False


async def test_running_job_is_not_manually_retryable() -> None:
    job, asset = job_pair()
    with pytest.raises(ValueError, match="not retryable"):
        await MediaRepository(Mock(spec=AsyncSession)).prepare_manual_retry(
            job, asset, datetime.now(UTC)
        )


async def test_duplicate_delivery_waits_for_durable_retry_deadline() -> None:
    job, asset = job_pair(MediaJobStatus.RETRYING.value)
    now = datetime.now(UTC)
    job.next_retry_at = now + timedelta(seconds=10)

    claimed = await repository_with_claim(job, asset).claim_job(job.id, now, 60)

    assert claimed is None
    assert job.attempts == 1


async def test_expired_running_lease_can_be_reclaimed() -> None:
    job, asset = job_pair()
    now = datetime.now(UTC)
    job.heartbeat_at = now - timedelta(seconds=61)

    claimed = await repository_with_claim(job, asset).claim_job(job.id, now, 60)

    assert claimed == (job, asset)
    assert job.status == MediaJobStatus.RUNNING.value
    assert job.attempts == 2
    assert job.heartbeat_at == now
