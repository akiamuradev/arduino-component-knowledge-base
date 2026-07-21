"""Audited media retention policy tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.media.models import MediaAsset
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.retention import MediaRetentionService
from arduino_component_kb.media.storage import MediaStorage, StorageObject


def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
    )


def rejected_asset(kind: str = "image") -> MediaAsset:
    now = datetime.now(UTC)
    return MediaAsset(
        id=uuid4(),
        owner_user_id=uuid4(),
        component_id=None,
        kind=kind,
        purpose="hero",
        alt_text="Rejected upload",
        status="rejected",
        bucket="ackb-media-quarantine",
        object_key=f"{kind}s/owner/asset/original",
        declared_mime="image/png" if kind == "image" else "video/mp4",
        declared_size_bytes=100,
        failure_code="image_decode_failed",
        upload_expires_at=now - timedelta(hours=1),
        created_at=now - timedelta(hours=2),
        updated_at=now - timedelta(hours=1),
    )


async def test_apply_cleans_rejected_original_and_partial_variants_with_system_audit() -> None:
    asset = rejected_asset()
    repository = Mock(spec=MediaRepository)
    repository.retention_candidates = AsyncMock(return_value=(asset,))
    repository.mark_storage_cleaned = Mock()
    repository.referenced_object_keys = AsyncMock(return_value=set())
    audit = Mock(spec=AuthRepository)
    audit.audit = AsyncMock()
    storage = Mock(spec=MediaStorage)
    storage.delete = AsyncMock()
    storage.list_objects = AsyncMock(return_value=())
    service = MediaRetentionService(repository, audit, storage, settings())

    report = await service.run(apply=True, now=datetime.now(UTC))

    assert report.assets_cleaned == 1
    assert report.objects_deleted == 4
    assert storage.delete.await_count == 4
    repository.mark_storage_cleaned.assert_called_once()
    assert audit.audit.await_args.kwargs["actor_type"] == "system"


async def test_dry_run_never_deletes_or_mutates() -> None:
    repository = Mock(spec=MediaRepository)
    repository.retention_candidates = AsyncMock(return_value=(rejected_asset("video"),))
    repository.mark_storage_cleaned = Mock()
    repository.referenced_object_keys = AsyncMock(return_value=set())
    audit = Mock(spec=AuthRepository)
    audit.audit = AsyncMock()
    storage = Mock(spec=MediaStorage)
    storage.delete = AsyncMock()
    storage.list_objects = AsyncMock(return_value=())

    report = await MediaRetentionService(repository, audit, storage, settings()).run(
        apply=False, now=datetime.now(UTC)
    )

    assert report.assets_eligible == 1
    assert report.assets_cleaned == 0
    storage.delete.assert_not_awaited()
    repository.mark_storage_cleaned.assert_not_called()
    audit.audit.assert_not_awaited()
    assert repository.retention_candidates.await_args.kwargs["lock"] is False


async def test_orphan_scan_deletes_only_old_unreferenced_objects() -> None:
    now = datetime.now(UTC)
    old = now - timedelta(hours=48)
    recent = now - timedelta(minutes=5)
    repository = Mock(spec=MediaRepository)
    repository.retention_candidates = AsyncMock(return_value=())
    repository.referenced_object_keys = AsyncMock(return_value={"ready.webp"})
    audit = Mock(spec=AuthRepository)
    audit.audit = AsyncMock()
    storage = Mock(spec=MediaStorage)
    storage.delete = AsyncMock()
    storage.list_objects = AsyncMock(
        side_effect=(
            (
                StorageObject("orphan.bin", old),
                StorageObject("ready.webp", old),
                StorageObject("recent.bin", recent),
            ),
            (),
        )
    )
    service = MediaRetentionService(repository, audit, storage, settings())

    report = await service.run(apply=True, now=now)

    assert report.orphans_deleted == 1
    storage.delete.assert_awaited_once_with("ackb-media-quarantine", "orphan.bin")
    assert audit.audit.await_args.kwargs["action"] == "media.retention_orphans_cleaned"
