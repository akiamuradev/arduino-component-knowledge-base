"""Real PostgreSQL proof for Redis loss and worker-restart recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.auth.models import User
from arduino_component_kb.catalog import models as catalog_models
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.dispatch.models import JobDispatch
from arduino_component_kb.dispatch.repository import DispatchRepository
from arduino_component_kb.imports.models import ImportJob, Source
from arduino_component_kb.imports.repository import ImportRepository
from arduino_component_kb.media.models import MediaAsset, MediaJob
from arduino_component_kb.media.repository import MediaRepository

registered_models = (catalog_models.Component,)


async def test_import_job_and_dispatch_are_one_transaction(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    job_id = None
    dispatch_id = None
    now = datetime.now(UTC)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            source = await session.scalar(select(Source).limit(1))
            assert source is not None
            user_id = uuid4()
            session.add(
                User(
                    id=user_id,
                    login=f"transaction-{user_id}",
                    display_name="Dispatch transaction",
                    password_hash="test-only-not-a-real-hash",  # noqa: S106
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            job = ImportRepository(session).add_job(
                source,
                "https://arduinomodules.info/ky-023-joystick-dual-axis-module/",
                user_id,
                f"transaction:{uuid4()}",
                4,
            )
            await session.flush()
            dispatch = await session.scalar(
                select(JobDispatch).where(
                    JobDispatch.job_type == "import",
                    JobDispatch.job_id == job.id,
                )
            )
            assert dispatch is not None
            assert job.status == "queued"
            assert dispatch.status == "pending"
            job_id = job.id
            dispatch_id = dispatch.id
            await transaction.rollback()

        assert job_id is not None
        assert dispatch_id is not None
        async with database.sessions() as verification:
            assert await verification.get(ImportJob, job_id) is None
            assert await verification.get(JobDispatch, dispatch_id) is None
    finally:
        await database.dispose()


async def test_media_job_and_dispatch_are_one_transaction(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    job_id = None
    dispatch_id = None
    asset_id = uuid4()
    now = datetime.now(UTC)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            user_id = uuid4()
            session.add(
                User(
                    id=user_id,
                    login=f"media-transaction-{user_id}",
                    display_name="Media dispatch transaction",
                    password_hash="test-only-not-a-real-hash",  # noqa: S106
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            asset = MediaAsset(
                id=asset_id,
                owner_user_id=user_id,
                component_id=None,
                kind="image",
                purpose="hero",
                alt_text="Transaction proof",
                status="pending",
                bucket="ackb-test-quarantine",
                object_key=f"dispatch/{asset_id}/original",
                declared_mime="image/png",
                declared_size_bytes=100,
                upload_expires_at=now + timedelta(minutes=5),
                created_at=now,
                updated_at=now,
            )
            session.add(asset)
            job = await MediaRepository(session).start_processing(asset, now, 4)
            dispatch = await session.scalar(
                select(JobDispatch).where(
                    JobDispatch.job_type == "media",
                    JobDispatch.job_id == job.id,
                )
            )
            assert dispatch is not None
            assert job.status == "queued"
            assert dispatch.status == "pending"
            assert dispatch.queue_name == "images"
            job_id = job.id
            dispatch_id = dispatch.id
            await transaction.rollback()

        assert job_id is not None
        assert dispatch_id is not None
        async with database.sessions() as verification:
            assert await verification.get(MediaAsset, asset_id) is None
            assert await verification.get(MediaJob, job_id) is None
            assert await verification.get(JobDispatch, dispatch_id) is None
    finally:
        await database.dispose()


async def _job_and_dispatch(
    session: AsyncSession,
    *,
    now: datetime,
    status: str,
    attempts: int,
    max_attempts: int,
) -> tuple[ImportJob, JobDispatch]:
    source_id = await session.scalar(select(Source.id).limit(1))
    assert source_id is not None
    user_id = uuid4()
    session.add(
        User(
            id=user_id,
            login=f"dispatch-{user_id}",
            display_name="Dispatch integration",
            password_hash="test-only-not-a-real-hash",  # noqa: S106
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    job = ImportJob(
        id=uuid4(),
        source_id=source_id,
        submitted_url="https://github.com/Seeed-Studio/wiki-documents",
        status=status,
        requested_by=user_id,
        idempotency_key=f"dispatch:{uuid4()}",
        attempts=0,
        max_attempts=max_attempts,
        created_at=now,
        updated_at=now,
        heartbeat_at=now,
    )
    dispatch = JobDispatch(
        id=uuid4(),
        job_type="import",
        job_id=job.id,
        queue_name="imports",
        status="delivered",
        attempts=attempts,
        max_attempts=max_attempts,
        next_attempt_at=now,
        delivered_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add_all((job, dispatch))
    await session.flush()
    return job, dispatch


async def test_redis_clear_redelivers_queued_job_without_changing_truth(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    now = datetime.now(UTC)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            job, dispatch = await _job_and_dispatch(
                session,
                now=now - timedelta(minutes=5),
                status="queued",
                attempts=1,
                max_attempts=4,
            )
            repository = DispatchRepository(session)

            recovered = await repository.recover_lost_deliveries(
                now=now,
                stale_delivery_seconds=60,
                import_lease_seconds=60,
                media_lease_seconds=60,
                limit=10,
            )
            intents = await repository.claim_due(
                now=now,
                limit=10,
                claim_lease_seconds=60,
            )
            await repository.mark_delivered(dispatch.id, now)

            assert recovered >= 1
            assert job.id in {item.job_id for item in intents}
            assert job.status == "queued"
            assert dispatch.status == "delivered"
            assert dispatch.attempts == 2
            await transaction.rollback()
    finally:
        await database.dispose()


async def test_worker_restart_redelivers_expired_running_lease(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    now = datetime.now(UTC)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            job, dispatch = await _job_and_dispatch(
                session,
                now=now - timedelta(minutes=5),
                status="running",
                attempts=1,
                max_attempts=4,
            )
            repository = DispatchRepository(session)

            recovered = await repository.recover_lost_deliveries(
                now=now,
                stale_delivery_seconds=60,
                import_lease_seconds=60,
                media_lease_seconds=60,
                limit=10,
            )
            intents = await repository.claim_due(
                now=now,
                limit=10,
                claim_lease_seconds=60,
            )

            assert recovered >= 1
            assert job.id in {item.job_id for item in intents}
            assert job.status == "running"
            assert dispatch.attempts == 2
            await transaction.rollback()
    finally:
        await database.dispose()


async def test_delivery_exhaustion_becomes_safe_explicitly_retryable_failure(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    now = datetime.now(UTC)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            job, dispatch = await _job_and_dispatch(
                session,
                now=now - timedelta(minutes=5),
                status="queued",
                attempts=4,
                max_attempts=4,
            )

            recovered = await DispatchRepository(session).recover_lost_deliveries(
                now=now,
                stale_delivery_seconds=60,
                import_lease_seconds=60,
                media_lease_seconds=60,
                limit=10,
            )

            assert recovered >= 1
            assert dispatch.status == "failed"
            assert dispatch.error_code == "dispatch_attempts_exhausted"
            assert job.status == "failed"
            assert job.error_code == "import_dispatch_exhausted"
            assert job.finished_at == now
            await transaction.rollback()
    finally:
        await database.dispose()
