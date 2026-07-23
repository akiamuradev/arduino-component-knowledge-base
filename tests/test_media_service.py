"""Presigned upload and confirmation policy tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.media.domain import (
    MAX_COMPONENT_IMAGES,
    MAX_COMPONENT_ORIGINAL_BYTES,
    ComponentMediaUsage,
    MediaKind,
    MediaNotFoundError,
    MediaQuotaError,
    MediaValidationError,
    UploadReservation,
)
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
    repository.lock_upload_reservations = AsyncMock()
    repository.count_pending = AsyncMock(return_value=0)
    repository.count_all_pending = AsyncMock(return_value=0)
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
        component_revision=None,
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
    repository.lock_upload_reservations = AsyncMock()
    repository.count_pending = AsyncMock(return_value=0)
    repository.count_all_pending = AsyncMock(return_value=0)
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
        component_revision=None,
        purpose="demo",
        alt_text="Video demonstration",
        attribution=None,
        declared_mime="video/mp4",
        declared_size_bytes=256 * 1024 * 1024,
        request_id="request-video",
    )

    assert result.reservation.object_key.startswith(f"videos/{actor.user_id}/")


async def test_reservation_quota_is_checked_under_global_transaction_lock() -> None:
    actor = teacher()
    call_order: list[str] = []

    def record_lock() -> None:
        call_order.append("lock")

    def count_owner(_: object) -> int:
        call_order.append("owner-count")
        return settings().media_pending_upload_limit

    repository = Mock(spec=MediaRepository)
    repository.lock_upload_reservations = AsyncMock(side_effect=record_lock)
    repository.count_pending = AsyncMock(side_effect=count_owner)
    repository.count_all_pending = AsyncMock()
    repository.create_reservation = AsyncMock()
    service = MediaService(
        repository,
        Mock(spec=AuthRepository),
        Mock(spec=MediaStorage),
        settings(),
    )

    with pytest.raises(MediaQuotaError):
        await service.reserve_upload(
            actor=actor,
            kind=MediaKind.IMAGE,
            component_id=None,
            component_revision=None,
            purpose="hero",
            alt_text="Arduino board",
            attribution=None,
            declared_mime="image/png",
            declared_size_bytes=100,
            request_id="request-quota",
        )

    assert call_order == ["lock", "owner-count"]
    repository.count_all_pending.assert_not_awaited()
    repository.create_reservation.assert_not_awaited()


async def test_reservation_enforces_global_pending_quota() -> None:
    actor = teacher()
    repository = Mock(spec=MediaRepository)
    repository.lock_upload_reservations = AsyncMock()
    repository.count_pending = AsyncMock(return_value=0)
    repository.count_all_pending = AsyncMock(
        return_value=settings().media_global_pending_upload_limit
    )
    repository.create_reservation = AsyncMock()
    service = MediaService(
        repository,
        Mock(spec=AuthRepository),
        Mock(spec=MediaStorage),
        settings(),
    )

    with pytest.raises(MediaQuotaError):
        await service.reserve_upload(
            actor=actor,
            kind=MediaKind.VIDEO,
            component_id=None,
            component_revision=None,
            purpose="demo",
            alt_text="Video demonstration",
            attribution=None,
            declared_mime="video/mp4",
            declared_size_bytes=1024,
            request_id="request-global-quota",
        )

    repository.create_reservation.assert_not_awaited()


async def test_asset_id_does_not_bypass_owner_authorization() -> None:
    actor = teacher()
    foreign_asset = MediaAsset(id=uuid4(), owner_user_id=uuid4(), kind="image")
    repository = Mock(spec=MediaRepository)
    repository.get_asset = AsyncMock(return_value=foreign_asset)
    audit = Mock(spec=AuthRepository)
    storage = Mock(spec=MediaStorage)
    service = MediaService(repository, audit, storage, settings())

    with pytest.raises(MediaNotFoundError):
        await service.visible_asset(actor, foreign_asset.id, MediaKind.IMAGE)


async def test_attached_reservation_requires_component_revision() -> None:
    repository = Mock(spec=MediaRepository)
    repository.lock_upload_reservations = AsyncMock()
    repository.count_pending = AsyncMock(return_value=0)
    repository.count_all_pending = AsyncMock(return_value=0)
    repository.create_reservation = AsyncMock()
    service = MediaService(
        repository,
        Mock(spec=AuthRepository),
        Mock(spec=MediaStorage),
        settings(),
    )

    with pytest.raises(MediaValidationError) as captured:
        await service.reserve_upload(
            actor=teacher(),
            kind=MediaKind.IMAGE,
            component_id=uuid4(),
            component_revision=None,
            purpose="product",
            alt_text="Top view",
            attribution=None,
            declared_mime="image/png",
            declared_size_bytes=100,
            request_id="missing-revision",
        )

    assert captured.value.code == "component_revision_required"
    repository.create_reservation.assert_not_awaited()


@pytest.mark.parametrize(
    ("usage", "kind", "declared_size", "expected_code"),
    (
        (
            ComponentMediaUsage(MAX_COMPONENT_IMAGES, 0, 1024),
            MediaKind.IMAGE,
            100,
            "media_component_count_exceeded",
        ),
        (
            ComponentMediaUsage(1, 0, MAX_COMPONENT_ORIGINAL_BYTES - 50),
            MediaKind.IMAGE,
            100,
            "media_component_size_exceeded",
        ),
    ),
)
async def test_component_media_quotas_are_enforced_before_reservation(
    usage: ComponentMediaUsage,
    kind: MediaKind,
    declared_size: int,
    expected_code: str,
) -> None:
    actor = teacher()
    repository = Mock(spec=MediaRepository)
    repository.lock_upload_reservations = AsyncMock()
    repository.count_pending = AsyncMock(return_value=0)
    repository.count_all_pending = AsyncMock(return_value=0)
    repository.lock_component_revision = AsyncMock(return_value=1)
    repository.component_usage = AsyncMock(return_value=usage)
    repository.create_reservation = AsyncMock()
    service = MediaService(
        repository,
        Mock(spec=AuthRepository),
        Mock(spec=MediaStorage),
        settings(),
    )

    with pytest.raises(MediaQuotaError) as captured:
        await service.reserve_upload(
            actor=actor,
            kind=kind,
            component_id=uuid4(),
            component_revision=1,
            purpose="hero",
            alt_text="Arduino board",
            attribution=None,
            declared_mime="image/png",
            declared_size_bytes=declared_size,
            request_id="request-component-quota",
        )

    assert captured.value.code == expected_code
    repository.create_reservation.assert_not_awaited()
