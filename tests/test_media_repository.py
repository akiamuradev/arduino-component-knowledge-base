"""Media repository locking and quota query regressions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.media.repository import MediaRepository


async def test_upload_reservations_use_a_transaction_advisory_lock() -> None:
    session = Mock(spec=AsyncSession)
    session.execute = AsyncMock()
    repository = MediaRepository(cast(AsyncSession, session))

    await repository.lock_upload_reservations()

    call = session.execute.await_args
    assert call is not None
    assert "pg_advisory_xact_lock" in str(call.args[0])


async def test_global_pending_count_has_no_owner_filter() -> None:
    session = Mock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=3)
    repository = MediaRepository(cast(AsyncSession, session))

    assert await repository.count_all_pending() == 3

    call = session.scalar.await_args
    assert call is not None
    sql = str(call.args[0])
    assert "media_assets.status" in sql
    assert "media_assets.upload_expires_at > now()" in sql
    assert "owner_user_id" not in sql


async def test_component_usage_counts_live_and_ready_assets() -> None:
    result = Mock()
    result.one.return_value = (2, 1, 4096)
    session = Mock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=result)
    repository = MediaRepository(cast(AsyncSession, session))

    usage = await repository.component_usage(uuid4())

    assert (usage.images, usage.videos, usage.original_bytes) == (2, 1, 4096)
    call = session.execute.await_args
    assert call is not None
    sql = str(call.args[0])
    assert "media_assets.component_id" in sql
    assert "media_assets.upload_expires_at > now()" in sql
    assert "media_assets.status" in sql


async def test_retention_dry_run_does_not_lock_candidates() -> None:
    session = Mock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=())
    repository = MediaRepository(cast(AsyncSession, session))

    await repository.retention_candidates(datetime.now(UTC), 100, lock=False)

    call = session.scalars.await_args
    assert call is not None
    sql = str(call.args[0])
    assert "media_assets.storage_cleaned_at IS NULL" in sql
    assert "media_assets.updated_at <=" in sql
    assert "FOR UPDATE" not in sql
