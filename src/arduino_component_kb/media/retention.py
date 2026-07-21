"""Audited cleanup of expired, rejected, partial, and orphaned media objects."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.media.models import MediaAsset
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.storage import MediaStorage, MinioStorage, StorageObject


@dataclass(frozen=True, slots=True)
class RetentionReport:
    assets_eligible: int = 0
    assets_cleaned: int = 0
    orphans_eligible: int = 0
    orphans_deleted: int = 0
    objects_deleted: int = 0


class MediaRetentionService:
    def __init__(
        self,
        repository: MediaRepository,
        audit: AuthRepository,
        storage: MediaStorage,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.audit = audit
        self.storage = storage
        self.settings = settings

    async def run(self, *, apply: bool, now: datetime | None = None) -> RetentionReport:
        current = now or datetime.now(UTC)
        cutoff = current - timedelta(hours=self.settings.media_retention_grace_hours)
        candidates = await self.repository.retention_candidates(
            cutoff, self.settings.media_retention_batch_size, lock=apply
        )
        assets_cleaned = 0
        objects_deleted = 0
        if apply:
            for asset in candidates:
                objects = _asset_objects(asset, self.settings.minio_variants_bucket)
                for bucket, object_key in objects:
                    await self.storage.delete(bucket, object_key)
                reason = (
                    "upload_expired_retention"
                    if asset.status == "pending"
                    else asset.failure_code or "media_rejected"
                )
                self.repository.mark_storage_cleaned(asset, reason=reason, now=current)
                await self.audit.audit(
                    now=current,
                    actor_user_id=None,
                    actor_type="system",
                    action="media.retention_asset_cleaned",
                    object_type="media_asset",
                    object_id=asset.id,
                    request_id=None,
                    outcome="success",
                    details={"reason": reason, "objects_deleted": len(objects)},
                )
                assets_cleaned += 1
                objects_deleted += len(objects)

        orphans_eligible = 0
        orphans_deleted = 0
        for bucket in (
            self.settings.minio_quarantine_bucket,
            self.settings.minio_variants_bucket,
        ):
            listed = await self.storage.list_objects(
                bucket, self.settings.media_retention_scan_limit
            )
            old_objects = tuple(item for item in listed if _is_older_than(item, cutoff))
            referenced = await self.repository.referenced_object_keys(
                bucket, frozenset(item.object_key for item in old_objects)
            )
            orphans = tuple(item for item in old_objects if item.object_key not in referenced)
            orphans_eligible += len(orphans)
            if not apply or not orphans:
                continue
            for item in orphans:
                await self.storage.delete(bucket, item.object_key)
            await self.audit.audit(
                now=current,
                actor_user_id=None,
                actor_type="system",
                action="media.retention_orphans_cleaned",
                object_type="media_bucket",
                object_id=None,
                request_id=None,
                outcome="success",
                details={"bucket": bucket, "objects_deleted": len(orphans)},
            )
            orphans_deleted += len(orphans)
            objects_deleted += len(orphans)

        return RetentionReport(
            assets_eligible=len(candidates),
            assets_cleaned=assets_cleaned,
            orphans_eligible=orphans_eligible,
            orphans_deleted=orphans_deleted,
            objects_deleted=objects_deleted,
        )


def _asset_objects(asset: MediaAsset, variants_bucket: str) -> tuple[tuple[str, str], ...]:
    variants: tuple[str, ...]
    if asset.kind == "video":
        variants = (
            f"videos/{asset.id}/video_720p.mp4",
            f"videos/{asset.id}/poster.webp",
        )
    else:
        variants = tuple(f"images/{asset.id}/{width}.webp" for width in ("320w", "800w", "1600w"))
    return ((asset.bucket, asset.object_key),) + tuple(
        (variants_bucket, object_key) for object_key in variants
    )


def _is_older_than(item: StorageObject, cutoff: datetime) -> bool:
    modified = item.last_modified
    if modified.tzinfo is None:
        modified = modified.replace(tzinfo=UTC)
    return modified <= cutoff


async def _run(settings: Settings, *, apply: bool) -> RetentionReport:
    database = Database(settings)
    storage = MinioStorage(settings)
    try:
        async with database.sessions() as session, session.begin():
            return await MediaRetentionService(
                MediaRepository(session), AuthRepository(session), storage, settings
            ).run(apply=apply)
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or clean retained media objects")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete eligible objects; without this flag the command is a dry run",
    )
    arguments = parser.parse_args()
    report = asyncio.run(_run(Settings(), apply=arguments.apply))
    mode = "apply" if arguments.apply else "dry-run"
    print(
        f"media retention {mode}: assets_eligible={report.assets_eligible} "
        f"assets_cleaned={report.assets_cleaned} "
        f"orphans_eligible={report.orphans_eligible} "
        f"orphans_deleted={report.orphans_deleted} "
        f"objects_deleted={report.objects_deleted}"
    )
