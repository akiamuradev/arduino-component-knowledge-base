"""PostgreSQL query budget for public catalog page assembly."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func

from arduino_component_kb.auth.models import User
from arduino_component_kb.catalog.domain import ComponentChangeAction, ComponentStatus, Difficulty
from arduino_component_kb.catalog.models import (
    Category,
    Component,
    ComponentRevision,
    PublishedSearchDocument,
)
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.media.models import MediaAsset, MediaVariant

pytestmark = pytest.mark.integration


def _snapshot(category_id: UUID, asset_id: UUID, index: int) -> dict[str, object]:
    return {
        "slug": f"query-budget-{index}",
        "title": f"Query budget component {index}",
        "aliases": [],
        "manufacturer": None,
        "model": None,
        "primary_category_id": str(category_id),
        "tags": [],
        "summary": "Published component used to verify the catalog query budget.",
        "description": "Stable public snapshot for the aggregate catalog reader.",
        "purpose": None,
        "usage_notes": None,
        "safety_notes": None,
        "difficulty": Difficulty.BEGINNER.value,
        "teacher_notes": None,
        "manual_original": True,
        "specifications": [],
        "compatibility": [],
        "code_examples": [],
        "sources": [],
        "media": [
            {
                "asset_id": str(asset_id),
                "kind": "image",
                "purpose": "product",
                "alt_text": f"Component {index}",
                "caption": None,
                "display_order": 0,
                "is_primary": True,
                "width": 1200,
                "height": 900,
                "variants": [
                    {
                        "name": "800w",
                        "mime": "image/webp",
                        "width": 800,
                        "height": 600,
                        "sha256": f"{index + 20:064x}",
                    }
                ],
            }
        ],
    }


async def test_catalog_page_query_count_does_not_grow_per_card(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            now = datetime.now(UTC)
            suffix = uuid4().hex
            user_id = uuid4()
            category_id = uuid4()
            session.add(
                User(
                    id=user_id,
                    login=f"query-budget-{suffix}",
                    display_name="Query budget",
                    password_hash=f"integration-{suffix}",
                    status="active",
                    created_at=now,
                    updated_at=now,
                    last_login_at=None,
                )
            )
            session.add(
                Category(
                    id=category_id,
                    key=f"query-budget-{suffix}",
                    name="Query budget",
                    description=None,
                    parent_id=None,
                    position=9900,
                    is_active=True,
                )
            )
            for index in range(3):
                component_id = uuid4()
                asset_id = uuid4()
                title = f"Query budget component {index}"
                summary = "Published component used to verify the catalog query budget."
                session.add(
                    Component(
                        id=component_id,
                        slug=f"query-budget-{suffix}-{index}",
                        status=ComponentStatus.PUBLISHED.value,
                        archived_from_status=None,
                        title=title,
                        manufacturer=None,
                        model=None,
                        normalized_manufacturer=None,
                        normalized_model=None,
                        summary=summary,
                        description="Stable public snapshot for the aggregate catalog reader.",
                        purpose=None,
                        usage_notes=None,
                        safety_notes=None,
                        difficulty=Difficulty.BEGINNER.value,
                        teacher_notes=None,
                        primary_category_id=category_id,
                        manual_original=True,
                        created_by=user_id,
                        updated_by=user_id,
                        published_at=now + timedelta(seconds=index),
                        created_at=now,
                        updated_at=now,
                        revision=1,
                    )
                )
                session.add(
                    ComponentRevision(
                        id=uuid4(),
                        component_id=component_id,
                        revision=1,
                        status=ComponentStatus.PUBLISHED.value,
                        previous_status=ComponentStatus.APPROVED.value,
                        action=ComponentChangeAction.PUBLISHED.value,
                        change_summary="Карточка опубликована",
                        content_json=_snapshot(category_id, asset_id, index),
                        actor_id=user_id,
                        created_at=now,
                    )
                )
                session.add(
                    PublishedSearchDocument(
                        component_id=component_id,
                        revision=1,
                        category_id=category_id,
                        difficulty=Difficulty.BEGINNER.value,
                        title=title,
                        aliases_text="",
                        manufacturer="",
                        model="",
                        summary=summary,
                        tags_text="",
                        search_text=f"{title} {summary}",
                        search_vector=cast(str, func.to_tsvector("simple", f"{title} {summary}")),
                        published_at=now + timedelta(seconds=index),
                    )
                )
                session.add(
                    MediaAsset(
                        id=asset_id,
                        owner_user_id=user_id,
                        component_id=component_id,
                        kind="image",
                        purpose="product",
                        alt_text=f"Component {index}",
                        caption=None,
                        display_order=0,
                        is_primary=True,
                        attribution=None,
                        status="ready",
                        bucket="query-budget-originals",
                        object_key=f"{suffix}/{index}.png",
                        declared_mime="image/png",
                        declared_size_bytes=100,
                        detected_mime="image/png",
                        size_bytes=100,
                        sha256=f"{index + 10:064x}",
                        phash=f"{index + 10:016x}",
                        width=1200,
                        height=900,
                        duration_ms=None,
                        video_codec=None,
                        audio_codec=None,
                        frame_rate=None,
                        failure_code=None,
                        upload_expires_at=now + timedelta(minutes=15),
                        created_at=now,
                        updated_at=now,
                        storage_cleaned_at=None,
                    )
                )
                session.add(
                    MediaVariant(
                        id=uuid4(),
                        asset_id=asset_id,
                        variant="800w",
                        bucket="query-budget-variants",
                        object_key=f"{suffix}/{index}-800w.webp",
                        mime="image/webp",
                        size_bytes=80,
                        sha256=f"{index + 20:064x}",
                        width=800,
                        height=600,
                        duration_ms=None,
                        video_codec=None,
                        audio_codec=None,
                        frame_rate=None,
                    )
                )
            await session.flush()

            statements: list[str] = []

            def record_query(
                _connection: object,
                _cursor: object,
                statement: str,
                _parameters: object,
                _context: object,
                _executemany: bool,
            ) -> None:
                statements.append(statement)

            listener = cast(Callable[..., None], record_query)
            event.listen(database.engine.sync_engine, "before_cursor_execute", listener)
            try:
                cards, total = await CatalogService(session).list_published(
                    None, category_id, None, 3
                )
            finally:
                event.remove(database.engine.sync_engine, "before_cursor_execute", listener)

            assert total == 3
            assert len(cards) == 3
            assert all(len(card.media) == 1 for card in cards)
            assert len(statements) == 6
            await transaction.rollback()
    finally:
        await database.dispose()
