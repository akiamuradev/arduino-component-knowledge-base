"""Real PostgreSQL aggregate checks for multiple component images."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.models import User
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.catalog.domain import (
    CatalogValidationError,
    ComponentMediaNotFoundError,
    ComponentStatus,
    Difficulty,
    DraftData,
    RevisionConflictError,
)
from arduino_component_kb.catalog.models import Category, ComponentRevision
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.media.domain import ComponentImageMutation, MediaKind
from arduino_component_kb.media.models import MediaVariant
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.service import MediaService
from arduino_component_kb.media.storage import MediaStorage


def _draft(category_id: UUID, suffix: str) -> DraftData:
    return DraftData(
        slug=f"multiple-images-{suffix}",
        title="Multiple image component",
        aliases=(),
        manufacturer=None,
        model=None,
        primary_category_id=category_id,
        tags=(),
        summary="A sufficiently detailed component summary for integration.",
        description="A publishable component with an immutable image gallery.",
        purpose=None,
        usage_notes=None,
        safety_notes=None,
        difficulty=Difficulty.BEGINNER,
        teacher_notes=None,
        manual_original=True,
    )


def _actor(user_id: UUID) -> Principal:
    return Principal(
        user_id=user_id,
        login="multiple-images",
        display_name="Multiple images",
        roles=frozenset({Role.TEACHER}),
        session_id=uuid4(),
        csrf_hash="integration",
        expires_at=datetime.max.replace(tzinfo=UTC),
    )


async def test_image_aggregate_order_primary_publish_and_snapshot(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            now = datetime.now(UTC)
            user_id = uuid4()
            category_id = uuid4()
            suffix = uuid4().hex
            session.add_all(
                (
                    User(
                        id=user_id,
                        login=f"multiple-images-{suffix}",
                        display_name="Multiple image reviewer",
                        password_hash=f"integration-{suffix}",
                        status="active",
                        created_at=now,
                        updated_at=now,
                        last_login_at=None,
                    ),
                    Category(
                        id=category_id,
                        key=f"multiple-images-{suffix}",
                        name="Multiple images",
                        description=None,
                        parent_id=None,
                        position=9000,
                        is_active=True,
                    ),
                )
            )
            await session.flush()
            catalog = CatalogService(session)
            card = await catalog.create(_draft(category_id, suffix), user_id)
            assert card.revision == 1
            assert card.media == ()
            with pytest.raises(CatalogValidationError) as missing_image:
                await catalog.transition(
                    card.id,
                    card.revision,
                    ComponentStatus.PUBLISHED,
                    user_id,
                )
            assert missing_image.value.code == "component_image_required"

            storage = Mock(spec=MediaStorage)
            storage.presigned_put = AsyncMock(
                side_effect=(
                    "https://storage.invalid/first",
                    "https://storage.invalid/second",
                )
            )
            media = MediaService(
                MediaRepository(session),
                AuthRepository(session),
                storage,
                integration_settings,
            )
            first = await media.reserve_upload(
                actor=_actor(user_id),
                kind=MediaKind.IMAGE,
                component_id=card.id,
                component_revision=card.revision,
                purpose="product",
                alt_text="First view",
                attribution=None,
                declared_mime="image/png",
                declared_size_bytes=100,
                request_id="multiple-images-first",
            )
            assert first.component_revision == 2
            second = await media.reserve_upload(
                actor=_actor(user_id),
                kind=MediaKind.IMAGE,
                component_id=card.id,
                component_revision=2,
                purpose="detail",
                alt_text="Second view",
                attribution=None,
                declared_mime="image/png",
                declared_size_bytes=100,
                request_id="multiple-images-second",
            )
            assert second.component_revision == 3

            repository = MediaRepository(session)
            assets = await repository.component_assets(
                card.id,
                kind=MediaKind.IMAGE,
                lock=True,
            )
            assert [item.display_order for item in assets] == [0, 1]
            assert [item.is_primary for item in assets] == [True, False]

            with pytest.raises(CatalogValidationError) as pending:
                await catalog.transition(card.id, 3, ComponentStatus.PUBLISHED, user_id)
            assert pending.value.code == "component_image_not_ready"

            assets[0].status = "rejected"
            assets[0].failure_code = "image_magic_invalid"
            await session.flush()
            with pytest.raises(CatalogValidationError) as rejected:
                await catalog.transition(card.id, 3, ComponentStatus.PUBLISHED, user_id)
            assert rejected.value.code == "component_image_not_ready"

            for index, asset in enumerate(assets):
                asset.status = "ready"
                asset.failure_code = None
                asset.detected_mime = "image/png"
                asset.size_bytes = 100
                asset.sha256 = f"{index + 1:064x}"
                asset.phash = f"{index + 1:016x}"
                asset.width = 640
                asset.height = 480
                session.add(
                    MediaVariant(
                        id=uuid4(),
                        asset_id=asset.id,
                        variant="320w",
                        bucket=integration_settings.minio_variants_bucket,
                        object_key=f"images/{asset.id}/320w.webp",
                        mime="image/webp",
                        size_bytes=64,
                        sha256=f"{index + 11:064x}",
                        width=320,
                        height=240,
                    )
                )
            await session.flush()
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    assets[1].is_primary = True
                    await session.flush()
            await session.refresh(assets[1])
            assert assets[1].is_primary is False
            for asset in assets:
                asset.is_primary = False
            await session.flush()
            with pytest.raises(CatalogValidationError) as missing_primary:
                await catalog.transition(card.id, 3, ComponentStatus.PUBLISHED, user_id)
            assert missing_primary.value.code == "component_primary_image_required"

            reordered = await catalog.mutate_images(
                card.id,
                3,
                (
                    ComponentImageMutation(
                        assets[1].id,
                        "product",
                        "Second view",
                        "Primary view",
                    ),
                    ComponentImageMutation(
                        assets[0].id,
                        "detail",
                        "First view",
                        None,
                    ),
                ),
                assets[1].id,
                user_id,
            )
            assert reordered.revision == 4
            assert [item.asset_id for item in reordered.media] == [
                assets[1].id,
                assets[0].id,
            ]
            assert [item.is_primary for item in reordered.media] == [True, False]
            with pytest.raises(RevisionConflictError):
                await catalog.mutate_images(
                    card.id,
                    3,
                    (
                        ComponentImageMutation(
                            assets[0].id,
                            "product",
                            "Stale first view",
                            None,
                        ),
                        ComponentImageMutation(
                            assets[1].id,
                            "detail",
                            "Stale second view",
                            None,
                        ),
                    ),
                    assets[0].id,
                    user_id,
                )

            published = await catalog.transition(
                card.id,
                reordered.revision,
                ComponentStatus.PUBLISHED,
                user_id,
            )
            assert published.revision == 5
            await session.flush()
            snapshot = await session.scalar(
                select(ComponentRevision).where(
                    ComponentRevision.component_id == card.id,
                    ComponentRevision.revision == published.revision,
                )
            )
            assert snapshot is not None
            manifest = cast(list[dict[str, object]], snapshot.content_json["media"])
            assert [item["asset_id"] for item in manifest] == [
                str(assets[1].id),
                str(assets[0].id),
            ]
            assert manifest[0]["is_primary"] is True
            rendered = str(manifest)
            assert "object_key" not in rendered
            assert integration_settings.minio_variants_bucket not in rendered

            changed_draft = await catalog.mutate_images(
                card.id,
                published.revision,
                (
                    ComponentImageMutation(
                        assets[0].id,
                        "product",
                        "First view changed in draft",
                        "New draft primary",
                    ),
                    ComponentImageMutation(
                        assets[1].id,
                        "detail",
                        "Second view changed in draft",
                        None,
                    ),
                ),
                assets[0].id,
                user_id,
            )
            assert changed_draft.status is ComponentStatus.DRAFT
            public = await catalog.get_published(card.data.slug)
            assert public.revision == 5
            assert [item.asset_id for item in public.media] == [
                assets[1].id,
                assets[0].id,
            ]
            assert public.media[0].alt_text == "Second view"
            assert public.media[0].is_primary is True

            detached = await catalog.mutate_images(
                card.id,
                changed_draft.revision,
                (
                    ComponentImageMutation(
                        assets[1].id,
                        "product",
                        "Only remaining view",
                        None,
                    ),
                ),
                None,
                user_id,
            )
            assert len(detached.media) == 1
            assert detached.media[0].asset_id == assets[1].id
            assert detached.media[0].is_primary is True
            assert assets[0].component_id is None

            await transaction.rollback()
    finally:
        await database.dispose()


async def test_duplicate_merge_combines_media_and_hides_foreign_assets(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            now = datetime.now(UTC)
            user_id = uuid4()
            category_id = uuid4()
            suffix = uuid4().hex
            session.add_all(
                (
                    User(
                        id=user_id,
                        login=f"media-merge-{suffix}",
                        display_name="Media merge reviewer",
                        password_hash=f"integration-{suffix}",
                        status="active",
                        created_at=now,
                        updated_at=now,
                        last_login_at=None,
                    ),
                    Category(
                        id=category_id,
                        key=f"media-merge-{suffix}",
                        name="Media merge",
                        description=None,
                        parent_id=None,
                        position=9001,
                        is_active=True,
                    ),
                )
            )
            await session.flush()
            catalog = CatalogService(session)
            left = await catalog.create(_draft(category_id, f"left-{suffix}"), user_id)
            right = await catalog.create(_draft(category_id, f"right-{suffix}"), user_id)
            storage = Mock(spec=MediaStorage)
            storage.presigned_put = AsyncMock(
                side_effect=tuple(f"https://storage.invalid/{suffix}/{index}" for index in range(4))
            )
            media = MediaService(
                MediaRepository(session),
                AuthRepository(session),
                storage,
                integration_settings,
            )
            actor = _actor(user_id)

            revisions = {left.id: left.revision, right.id: right.revision}
            for component, label in ((left, "left"), (right, "right")):
                for position in range(2):
                    reservation = await media.reserve_upload(
                        actor=actor,
                        kind=MediaKind.IMAGE,
                        component_id=component.id,
                        component_revision=revisions[component.id],
                        purpose="product" if position == 0 else "detail",
                        alt_text=f"{label} image {position}",
                        attribution=None,
                        declared_mime="image/png",
                        declared_size_bytes=100,
                        request_id=f"media-merge-{suffix}-{label}-{position}",
                    )
                    assert reservation.component_revision is not None
                    revisions[component.id] = reservation.component_revision

            repository = MediaRepository(session)
            left_assets = await repository.component_assets(
                left.id,
                kind=MediaKind.IMAGE,
                lock=True,
            )
            right_assets = await repository.component_assets(
                right.id,
                kind=MediaKind.IMAGE,
                lock=True,
            )
            for index, asset in enumerate((*left_assets, *right_assets), start=1):
                asset.status = "ready"
                asset.detected_mime = "image/png"
                asset.size_bytes = 100
                asset.sha256 = f"{index:064x}"
                asset.phash = f"{index:016x}"
                asset.width = 640
                asset.height = 480
            await session.flush()

            with pytest.raises(ComponentMediaNotFoundError):
                await catalog.mutate_images(
                    left.id,
                    revisions[left.id],
                    (
                        ComponentImageMutation(
                            right_assets[0].id,
                            "detail",
                            "Foreign image",
                            None,
                        ),
                    ),
                    right_assets[0].id,
                    user_id,
                )

            before_left, before_right, merged = await catalog.resolve_duplicate_pair(
                left.id,
                right.id,
                revisions[left.id],
                revisions[right.id],
                left.id,
                {},
                user_id,
                merge_fields=False,
            )
            assert len(before_left.media) == 2
            assert len(before_right.media) == 2
            assert [item.asset_id for item in merged.media] == [
                item.id for item in (*left_assets, *right_assets)
            ]
            assert [item.display_order for item in merged.media] == [0, 1, 2, 3]
            assert [item.is_primary for item in merged.media] == [True, False, False, False]
            assert all(asset.component_id == left.id for asset in (*left_assets, *right_assets))

            await transaction.rollback()
    finally:
        await database.dispose()
