"""Presigned upload and confirmation policy tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.media.domain import MediaKind, MediaValidationError, UploadReservation
from arduino_component_kb.media.models import MediaAsset
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.service import MediaService
from arduino_component_kb.media.storage import MediaStorage, ObjectMetadata


def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
    )


def teacher() -> Principal:
    return Principal(
        user_id=uuid4(),
        login="teacher",
        display_name="Teacher",
        roles=frozenset({Role.TEACHER}),
        session_id=uuid4(),
        csrf_hash="csrf-hash",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


async def test_reservation_uses_private_quarantine_and_presigned_put() -> None:
    actor = teacher()
    repository = Mock(spec=MediaRepository)
    repository.count_pending = AsyncMock(return_value=0)
    repository.create_reservation = AsyncMock(
        side_effect=lambda **values: UploadReservation(
            values["asset_id"],
            values["bucket"],
            values["object_key"],
            values["declared_mime"],
            values["expires_at"],
        )
    )
    audit = Mock(spec=AuthRepository)
    audit.audit = AsyncMock()
    storage = Mock(spec=MediaStorage)
    storage.presigned_put = AsyncMock(return_value="https://minio.invalid/signed-placeholder")
    service = MediaService(repository, audit, storage, settings())

    result = await service.reserve_upload(
        actor=actor,
        kind=MediaKind.IMAGE,
        component_id=None,
        purpose="hero",
        alt_text="Arduino board",
        attribution=None,
        declared_mime="image/png",
        declared_size_bytes=100,
        request_id="request-1",
    )

    assert result.reservation.bucket == "ackb-media-quarantine"
    assert str(actor.user_id) in result.reservation.object_key
    storage.presigned_put.assert_awaited_once()
    audit.audit.assert_awaited_once()


async def test_confirmation_rejects_size_mismatch_before_queueing() -> None:
    actor = teacher()
    now = datetime.now(UTC)
    asset = MediaAsset(
        id=uuid4(),
        owner_user_id=actor.user_id,
        component_id=None,
        kind="image",
        purpose="hero",
        alt_text="Arduino board",
        attribution=None,
        status="pending",
        bucket="ackb-media-quarantine",
        object_key="images/example/original",
        declared_mime="image/png",
        declared_size_bytes=100,
        upload_expires_at=now + timedelta(minutes=5),
        created_at=now,
        updated_at=now,
    )
    repository = Mock(spec=MediaRepository)
    repository.lock_asset = AsyncMock(return_value=asset)
    repository.start_processing = AsyncMock()
    audit = Mock(spec=AuthRepository)
    audit.audit = AsyncMock()
    storage = Mock(spec=MediaStorage)
    storage.stat = AsyncMock(return_value=ObjectMetadata(size=99, content_type="image/png"))
    service = MediaService(repository, audit, storage, settings())

    with pytest.raises(MediaValidationError) as captured:
        await service.confirm_upload(actor=actor, asset_id=asset.id, request_id="request-2")

    assert captured.value.code == "uploaded_size_mismatch"
    assert asset.status == "rejected"
    repository.start_processing.assert_not_awaited()


async def test_video_reservation_uses_video_limits_and_prefix() -> None:
    actor = teacher()
    repository = Mock(spec=MediaRepository)
    repository.count_pending = AsyncMock(return_value=0)
    repository.create_reservation = AsyncMock(
        side_effect=lambda **values: UploadReservation(
            values["asset_id"],
            values["bucket"],
            values["object_key"],
            values["declared_mime"],
            values["expires_at"],
        )
    )
    audit = Mock(spec=AuthRepository)
    audit.audit = AsyncMock()
    storage = Mock(spec=MediaStorage)
    storage.presigned_put = AsyncMock(return_value="https://minio.invalid/video-placeholder")
    service = MediaService(repository, audit, storage, settings())

    result = await service.reserve_upload(
        actor=actor,
        kind=MediaKind.VIDEO,
        component_id=None,
        purpose="demo",
        alt_text="Video demonstration",
        attribution=None,
        declared_mime="video/mp4",
        declared_size_bytes=256 * 1024 * 1024,
        request_id="request-video",
    )

    assert result.reservation.object_key.startswith(f"videos/{actor.user_id}/")
