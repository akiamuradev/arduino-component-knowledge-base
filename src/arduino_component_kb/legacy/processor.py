"""Restartable worker: bounded temporary downloads, one catalog transaction per item."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4
from zipfile import ZipFile

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.legacy_imports import audit, bundle_items, key
from arduino_component_kb.catalog.models import Component
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.dispatch.repository import DispatchRepository
from arduino_component_kb.legacy.models import LegacyBundle, LegacyItem, LegacySourceLink
from arduino_component_kb.legacy.parser import (
    PARSER_VERSION,
    SOURCE_NAME,
    XLSX_LIMIT,
    ZIP_LIMIT,
    Analysis,
    LegacyInputError,
    Target,
    analyze,
    digest,
    file_hash,
)
from arduino_component_kb.legacy.planning import (
    candidates,
    category_id,
    draft_data,
    exceeds_draft_limits,
    merge_data,
    review_hash,
)
from arduino_component_kb.media.domain import MediaKind, MediaValidationError
from arduino_component_kb.media.images import detect_magic, process_image
from arduino_component_kb.media.models import MediaAsset, MediaJob
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.storage import MediaStorage, MinioStorage


def stored_plan_hash(bundle: LegacyBundle, items: list[LegacyItem]) -> str:
    return digest(
        [
            bundle.zip_sha256,
            bundle.xlsx_sha256,
            bundle.parser_version,
            [[i.payload, i.candidates] for i in sorted(items, key=lambda i: i.position)],
        ]
    )


async def save_analysis(session: AsyncSession, bundle: LegacyBundle, result: Analysis) -> None:
    items: list[LegacyItem] = []
    for position, target in enumerate(result.targets):
        matches = await candidates(session, target)
        previous = await session.get(LegacySourceLink, target.identity)
        decision = (
            "skip"
            if previous
            else "review"
            if matches or target.match == "review" or exceeds_draft_limits(target)
            else "create"
        )
        item = LegacyItem(
            id=uuid4(),
            bundle_id=bundle.id,
            identity=target.identity,
            position=position,
            payload=target.model_dump(mode="json"),
            candidates=matches,
            decision=decision,
            status="needs_review" if decision == "review" else "planned",
            warnings=[
                *target.warnings,
                *(["draft_limits_review_required"] if exceeds_draft_limits(target) else []),
            ],
            result_id=previous.component_id if previous else None,
        )
        session.add(item)
        items.append(item)
    bundle.zip_sha256 = result.zip_sha256
    bundle.xlsx_sha256 = result.xlsx_sha256
    bundle.parser_version = result.parser_version
    bundle.statistics = result.statistics
    bundle.plan_hash = stored_plan_hash(bundle, items)
    bundle.status = "ready"
    bundle.updated_at = datetime.now(UTC)
    await audit(session, bundle.owner_id, "analysis_completed", bundle.id)


async def ingest_images(
    session: AsyncSession,
    storage: MediaStorage,
    settings: Settings,
    bundle: LegacyBundle,
    item: LegacyItem,
    target: Target,
    component_id: UUID,
    zip_path: Path,
    xlsx_path: Path,
) -> None:
    repository = MediaRepository(session)
    usage = await repository.component_usage(component_id)
    existing = list(
        await session.scalars(
            select(MediaAsset).where(
                MediaAsset.component_id == component_id,
                MediaAsset.status != "rejected",
            )
        )
    )
    shas = {asset.sha256 for asset in existing if asset.sha256}
    phashes = [asset.phash for asset in existing if asset.phash]
    image_count = usage.images
    total_bytes = usage.original_bytes
    position = await repository.next_component_order(component_id, MediaKind.IMAGE)
    with ZipFile(zip_path) as archive, ZipFile(xlsx_path) as workbook:
        for ref in target.images:
            if ref.sha256 in shas:
                continue
            if image_count >= 12 or total_bytes + ref.size > 600 * 1024 * 1024:
                item.warnings = [*item.warnings, "image_card_limit_not_attached"]
                continue
            if ref.size > 8 * 1024 * 1024:
                item.warnings = [*item.warnings, "image_size_not_attached"]
                continue
            content = (archive if ref.origin == "zip" else workbook).read(ref.path)
            if len(content) != ref.size or hashlib.sha256(content).hexdigest() != ref.sha256:
                raise LegacyInputError("legacy_image_checksum_changed")
            try:
                mime = detect_magic(content)
                processed = await asyncio.to_thread(process_image, content, mime)
            except MediaValidationError as error:
                item.warnings = [*item.warnings, error.code]
                continue
            # Near-identical photos are retained for human review, not discarded on pHash alone.
            if any((int(processed.phash, 16) ^ int(p, 16)).bit_count() <= 4 for p in phashes):
                item.warnings = [*item.warnings, "near_duplicate_image_review"]
            asset_id = uuid4()
            object_key = f"images/{bundle.owner_id}/{asset_id}/original"
            await storage.upload(settings.minio_quarantine_bucket, object_key, content, mime)
            now = datetime.now(UTC)
            await repository.create_reservation(
                asset_id=asset_id,
                owner_id=bundle.owner_id,
                kind="image",
                component_id=component_id,
                purpose=ref.purpose,
                alt_text=target.title,
                caption=None,
                display_order=position,
                is_primary=image_count == 0,
                attribution=f"{SOURCE_NAME}; права требуют проверки",
                bucket=settings.minio_quarantine_bucket,
                object_key=object_key,
                declared_mime=mime,
                declared_size_bytes=len(content),
                now=now,
                expires_at=now + timedelta(minutes=15),
            )
            asset = await repository.get_asset(asset_id)
            assert asset is not None
            asset.sha256 = processed.sha256
            asset.phash = processed.phash
            await repository.start_processing(asset, now, settings.media_job_max_attempts)
            image_count += 1
            total_bytes += len(content)
            position += 1
            shas.add(ref.sha256)
            phashes.append(processed.phash)
    item.warnings = sorted(set(item.warnings))


async def apply_item(
    session: AsyncSession,
    bundle: LegacyBundle,
    item: LegacyItem,
    storage: MediaStorage,
    settings: Settings,
    zip_path: Path,
    xlsx_path: Path,
) -> None:
    # Serializes cross-bundle identity checks. Catalog's own locks protect manual edits.
    actor_id = bundle.confirmed_by
    if actor_id is None:
        raise LegacyInputError("legacy_confirmation_required")
    await session.execute(text("SELECT pg_advisory_xact_lock(71842102)"))
    previous = await session.get(LegacySourceLink, item.identity)
    if previous is not None or item.decision == "skip":
        item.result_id = previous.component_id if previous else item.result_id
        item.status = "skipped"
        await audit(session, actor_id, "item_skipped", item.id)
        return
    target = Target.model_validate(item.payload)
    current = await candidates(session, target)
    # Newly appearing/edited candidates invalidate this item, not already committed siblings.
    if digest(current) != digest(item.candidates):
        item.status = "needs_review"
        item.error_code = "legacy_catalog_changed"
        return
    service = CatalogService(session)
    incoming = draft_data(target, await category_id(session, target))
    if item.decision == "merge" and item.merge_id is not None:
        row = await session.scalar(
            select(Component)
            .where(
                Component.id == item.merge_id,
            )
            .with_for_update()
        )
        if (
            row is None
            or row.status != "draft"
            or row.published_at is not None
            or row.revision != item.merge_revision
            or row.edit_token != item.merge_edit_token
        ):
            item.status = "needs_review"
            item.error_code = "legacy_merge_changed"
            return
        card = await service.get_card(row.id)
        merged, warnings = merge_data(card.data, incoming)
        item.warnings = [*item.warnings, *warnings]
        card = await service.update(card.id, card.revision, merged, actor_id)
        action = "item_merged"
    elif item.decision == "create":
        card = await service.create(incoming, actor_id)
        action = "item_created"
    else:
        raise LegacyInputError("legacy_decision_invalid")
    session.add(
        LegacySourceLink(
            identity=item.identity, component_id=card.id, item_id=item.id, license_status="unknown"
        )
    )
    await ingest_images(
        session, storage, settings, bundle, item, target, card.id, zip_path, xlsx_path
    )
    await service.touch_media_attachment(card.id, card.revision, actor_id, datetime.now(UTC))
    item.result_id = card.id
    item.status = "applied"
    item.error_code = None
    await audit(session, actor_id, action, item.id)


async def process_bundle(bundle_id: UUID, settings: Settings) -> None:
    database = Database(settings)
    storage = MinioStorage(settings)
    lock_id = int.from_bytes(bundle_id.bytes[:8], "big", signed=True)
    try:
        async with database.engine.connect() as lease:
            acquired = await lease.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id}
            )
            if not acquired:
                return
            try:
                await run_bundle(database, storage, settings, bundle_id)
            finally:
                await lease.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})
    except Exception as error:
        # Do not log exception text: parsers/drivers may include private source contents.
        async with database.sessions() as session:
            bundle = await session.scalar(
                select(LegacyBundle)
                .where(
                    LegacyBundle.id == bundle_id,
                )
                .with_for_update()
            )
            if bundle is not None and bundle.status in {"analyzing", "applying"}:
                bundle.status = "failed"
                bundle.error_code = (
                    str(error)[:80]
                    if isinstance(error, LegacyInputError)
                    else "legacy_worker_failed"
                )
                bundle.updated_at = datetime.now(UTC)
                await audit(session, bundle.owner_id, "failed", bundle.id)
                await session.commit()
    finally:
        await database.dispose()


async def run_bundle(
    database: Database, storage: MediaStorage, settings: Settings, bundle_id: UUID
) -> None:
    async with database.sessions() as session:
        bundle = await session.get(LegacyBundle, bundle_id)
        if bundle is None or bundle.status not in {"analyzing", "applying"}:
            return
        phase = bundle.phase
        expected_zip, expected_xlsx = bundle.zip_sha256, bundle.xlsx_sha256
    with TemporaryDirectory(prefix="ackb-legacy-") as directory:
        zip_path, xlsx_path = Path(directory) / "source.zip", Path(directory) / "source.xlsx"
        await storage.download_to_file(
            settings.minio_legacy_bucket, key(bundle_id, "zip"), zip_path, ZIP_LIMIT
        )
        await storage.download_to_file(
            settings.minio_legacy_bucket, key(bundle_id, "xlsx"), xlsx_path, XLSX_LIMIT
        )
        if phase == "analysis":
            result = await asyncio.to_thread(analyze, zip_path, xlsx_path)
            async with database.sessions() as session:
                bundle = await session.scalar(
                    select(LegacyBundle)
                    .where(
                        LegacyBundle.id == bundle_id,
                    )
                    .with_for_update()
                )
                if bundle is None or bundle.status != "analyzing":
                    return
                if await bundle_items(session, bundle_id):
                    raise LegacyInputError("legacy_plan_already_exists")
                await save_analysis(session, bundle, result)
                await session.commit()
            return
        if file_hash(zip_path) != expected_zip or file_hash(xlsx_path) != expected_xlsx:
            raise LegacyInputError("legacy_source_checksum_changed")
        async with database.sessions() as session:
            bundle = await session.get(LegacyBundle, bundle_id)
            assert bundle is not None
            items = await bundle_items(session, bundle_id)
            if (
                bundle.parser_version != PARSER_VERSION
                or stored_plan_hash(bundle, items) != bundle.plan_hash
                or review_hash(bundle, items) != bundle.confirmed_hash
            ):
                raise LegacyInputError("legacy_plan_changed")
            item_ids = [i.id for i in items]
        for item_id in item_ids:
            async with database.sessions() as session:
                bundle = await session.scalar(
                    select(LegacyBundle)
                    .where(
                        LegacyBundle.id == bundle_id,
                    )
                    .with_for_update()
                )
                if bundle is None or bundle.status != "applying":
                    return
                item = await session.get(LegacyItem, item_id)
                assert item is not None
                if item.status in {"applied", "skipped", "needs_review", "failed"}:
                    continue
                pending = await session.scalar(
                    select(func.count())
                    .select_from(MediaJob)
                    .where(
                        MediaJob.status.in_(("queued", "running", "retrying")),
                    )
                )
                if pending is not None and pending >= 64:
                    # Persist backpressure; do not sleep while holding a database transaction.
                    dispatch = await DispatchRepository(session).reset(
                        job_type="legacy",
                        job_id=bundle.id,
                        queue_name="legacy",
                        max_attempts=4,
                        now=datetime.now(UTC),
                    )
                    dispatch.next_attempt_at = datetime.now(UTC) + timedelta(seconds=30)
                    bundle.updated_at = datetime.now(UTC)
                    await session.commit()
                    return
                item.status = "applying"
                try:
                    async with session.begin_nested():
                        await apply_item(
                            session, bundle, item, storage, settings, zip_path, xlsx_path
                        )
                except Exception:
                    # Roll back this entire item's card, provenance and job intents only.
                    item = await session.get(LegacyItem, item_id, populate_existing=True)
                    assert item is not None
                    item.status = "failed"
                    item.error_code = "legacy_item_failed"
                    await audit(session, bundle.owner_id, "item_failed", item.id)
                bundle.updated_at = datetime.now(UTC)
                await session.commit()
        async with database.sessions() as session:
            bundle = await session.scalar(
                select(LegacyBundle)
                .where(
                    LegacyBundle.id == bundle_id,
                )
                .with_for_update()
            )
            if bundle is not None and bundle.status == "applying":
                bundle.status = "completed"
                bundle.updated_at = datetime.now(UTC)
                await audit(session, bundle.owner_id, "completed", bundle.id)
                await session.commit()
