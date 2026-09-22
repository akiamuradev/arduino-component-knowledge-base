"""Editor acceptance in a newly created disposable database, never existing catalog data."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from pytest import MonkeyPatch
from sqlalchemy import func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from arduino_component_kb.api.catalog import _error
from arduino_component_kb.auth.domain import Role
from arduino_component_kb.auth.models import AuditEvent
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.catalog.domain import (
    CatalogCard,
    CatalogValidationError,
    ComponentStatus,
    Difficulty,
    DraftData,
    RevisionConflictError,
    TechnicalSpecification,
)
from arduino_component_kb.catalog.models import (
    Category,
    Component,
    ComponentProperty,
    ComponentRevision,
    PropertyDefinition,
    Unit,
)
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.catalog.synchronization import DocumentSynchronization
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.media.domain import ComponentImageMutation
from arduino_component_kb.media.models import MediaAsset
from arduino_component_kb.media.repository import MediaRepository


async def database_command(base: URL, name: str, *, drop: bool = False) -> None:
    assert name.startswith("ackb_editor_test_") and name.replace("_", "").isalnum()
    engine = create_async_engine(
        base.set(database="postgres").render_as_string(hide_password=False)
    )
    try:
        async with engine.connect() as raw:
            connection = await raw.execution_options(isolation_level="AUTOCOMMIT")
            statement = (
                f'DROP DATABASE "{name}" WITH (FORCE)' if drop else f'CREATE DATABASE "{name}"'
            )
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def exercise(settings: Settings) -> None:
    database = Database(settings)
    try:
        async with database.sessions() as session:
            now = datetime.now(UTC)
            actor = await AuthRepository(session).create_user(
                login="editor-acceptance",
                display_name="Editor test",
                password_hash="test-only",  # noqa: S106 -- disposable fixture, never authenticates
                roles=frozenset({Role.ADMINISTRATOR}),
                actor_id=None,
                now=now,
            )
            category = await session.scalar(select(Category.id).where(Category.key == "boards"))
            assert category is not None
            data = DraftData(
                slug="",
                title="Arduino UNO R3",
                aliases=(),
                manufacturer=None,
                model=None,
                primary_category_id=category,
                tags=(),
                summary="",
                description="",
                purpose=None,
                usage_notes=None,
                safety_notes=None,
                difficulty=Difficulty.BEGINNER,
                teacher_notes=None,
                manual_original=True,
            )
            sync = DocumentSynchronization(session)
            request_id = uuid4()
            card = await sync.create(request_id, data, actor.id)
            await session.commit()
            duplicate = await sync.create(request_id, data, actor.id)
            assert duplicate.id == card.id
            assert await session.scalar(select(func.count()).select_from(Component)) == 1
            component_id = card.id
            data = replace(data, slug=card.data.slug)
            first_token = card.edit_token
            for number in range(12):
                data = replace(data, description=f"Typed content {number} ")
                card = await sync.synchronize(
                    component_id, card.edit_token, data, (), None, actor.id
                )
                await session.commit()
                assert card.revision == 1
                assert card.data.description.endswith(" ")
            assert card.edit_token > first_token + 11
            assert await session.scalar(select(func.count()).select_from(ComponentRevision)) == 1
            assert await session.scalar(select(func.count()).select_from(AuditEvent)) == 1
            with pytest.raises(RevisionConflictError):
                await sync.synchronize(component_id, first_token, data, (), None, actor.id)
            await session.rollback()
            card = await sync.catalog.get_card(component_id)
            for aliases, code in (
                (
                    (
                        "Arduino Uno Rev3",
                        "Arduino UNO Rev3",
                        "UNO R3",
                        "Arduino Uno Revision 3",
                        "A000066",
                    ),
                    "duplicate_alias",
                ),
                (("Ａrduino", "arduino"), "duplicate_alias"),
            ):
                with pytest.raises(CatalogValidationError, match=code):
                    await sync.synchronize(
                        component_id,
                        card.edit_token,
                        replace(data, aliases=aliases),
                        (),
                        None,
                        actor.id,
                    )
                await session.rollback()
            with pytest.raises(CatalogValidationError, match="duplicate_tag"):
                await sync.synchronize(
                    component_id,
                    card.edit_token,
                    replace(data, tags=("UNO", "uno")),
                    (),
                    None,
                    actor.id,
                )
            await session.rollback()
            data = replace(data, summary="A complete summary for the review workflow.")
            card = await sync.synchronize(component_id, card.edit_token, data, (), None, actor.id)
            card = await sync.catalog.transition(
                component_id, card.revision, ComponentStatus.IN_REVIEW, actor.id
            )
            await session.commit()
            token = card.edit_token
            with pytest.raises(CatalogValidationError, match="component_image_required"):
                await sync.approve_and_publish(component_id, token, actor.id)
            await session.rollback()
            card = await sync.catalog.get_card(component_id)
            assert card.status is ComponentStatus.IN_REVIEW and card.revision == 2
            assert await session.scalar(select(func.count()).select_from(ComponentRevision)) == 2
            card = await sync.catalog.transition(
                component_id, card.revision, ComponentStatus.CHANGES_REQUESTED, actor.id
            )
            await session.commit()
            # Staged reservation itself has no component, token or history side effect.
            before_token, before_revision = card.edit_token, card.revision
            asset_id = uuid4()
            await MediaRepository(session).create_reservation(
                asset_id=asset_id,
                owner_id=actor.id,
                kind="image",
                component_id=None,
                purpose="product",
                alt_text="UNO",
                caption=None,
                display_order=0,
                is_primary=False,
                attribution=None,
                bucket="test-quarantine",
                object_key=f"test/{asset_id}",
                declared_mime="image/png",
                declared_size_bytes=128,
                now=now,
                expires_at=now + timedelta(minutes=10),
            )
            await session.commit()
            assert (await sync.catalog.get_card(component_id)).edit_token == before_token
            asset = await session.get(MediaAsset, asset_id)
            assert asset is not None
            asset.status = "ready"
            asset.detected_mime = "image/png"
            asset.size_bytes = 128
            asset.sha256 = "a" * 64
            asset.phash = "a" * 16
            asset.width, asset.height = 640, 480
            await session.commit()
            images = (ComponentImageMutation(asset_id, "product", "Arduino UNO", "Caption"),)
            card = await sync.synchronize(
                component_id, before_token, data, images, asset_id, actor.id
            )
            await session.commit()
            assert card.revision == before_revision
            assert card.media[0].caption == "Caption"
            card = await sync.catalog.transition(
                component_id, card.revision, ComponentStatus.IN_REVIEW, actor.id
            )
            await session.commit()
            card = await sync.approve_and_publish(component_id, card.edit_token, actor.id)
            await session.commit()
            assert card.status is ComponentStatus.PUBLISHED
            actions = list(
                await session.scalars(
                    select(ComponentRevision.action)
                    .where(
                        ComponentRevision.component_id == component_id,
                    )
                    .order_by(ComponentRevision.revision)
                )
            )
            assert actions[-2:] == ["component.approved", "component.published"]
            public_revision = card.revision
            card = await sync.synchronize(
                component_id,
                card.edit_token,
                replace(data, title="Unpublished local edit"),
                images,
                asset_id,
                actor.id,
            )
            await session.commit()
            assert card.revision == public_revision and card.status is ComponentStatus.DRAFT
            published = await sync.catalog._published_card(component_id)
            assert published is not None and published.data.title == "Arduino UNO R3"
            actor_id = actor.id

        # Independent transactions, not sequential calls on the same identity map.
        parallel_key = uuid4()

        async def parallel_create() -> CatalogCard:
            async with database.sessions() as parallel_session:
                result = await DocumentSynchronization(parallel_session).create(
                    parallel_key, replace(data, slug=""), actor_id
                )
                await parallel_session.commit()
                return result

        first, second = await asyncio.gather(parallel_create(), parallel_create())
        assert first.id == second.id

        async def competing_save(title: str) -> bool:
            async with database.sessions() as parallel_session:
                try:
                    await DocumentSynchronization(parallel_session).synchronize(
                        first.id,
                        first.edit_token,
                        replace(data, slug=first.data.slug, title=title),
                        (),
                        None,
                        actor_id,
                    )
                    await parallel_session.commit()
                    return True
                except RevisionConflictError:
                    await parallel_session.rollback()
                    return False

        assert sorted(await asyncio.gather(competing_save("First"), competing_save("Second"))) == [
            False,
            True,
        ]
        await exercise_diagnostics(database, data, actor_id)
    finally:
        await database.dispose()


async def exercise_diagnostics(database: Database, base: DraftData, actor_id: UUID) -> None:
    """Persist converted metadata, verify rollback and map the real driver constraint."""
    original = (
        TechnicalSpecification("diagnostic-flash", "Flash-память", "32 КБ", "32", "КБ", 0),
        TechnicalSpecification("diagnostic-voltage", "Питание", "5 V", "5", "V", 1),
        TechnicalSpecification("diagnostic-clock", "Тактовая частота", "16 МГц", "16", "МГц", 2),
        TechnicalSpecification("diagnostic-custom", "Custom", "4 widgets", "4", "widgets", 3),
    )
    converted = (
        replace(original[0], value_text="4 МБ", value_number="4", unit="МБ"),
        replace(original[1], value_text="5000 мВ", value_number="5000", unit="мВ"),
        *original[2:],
    )
    async with database.sessions() as session:
        service = CatalogService(session)
        first = await service.create(
            replace(base, slug="diagnostic-first", specifications=original), actor_id
        )
        second = await service.create(
            replace(base, slug="diagnostic-second", specifications=converted), actor_id
        )
        await session.commit()
        second_id = second.id
        second_token = second.edit_token
        first_slug = first.data.slug

    async with database.sessions() as session:
        rows = (
            await session.execute(
                select(ComponentProperty, PropertyDefinition, Unit)
                .join(PropertyDefinition, PropertyDefinition.id == ComponentProperty.definition_id)
                .join(Unit, Unit.id == PropertyDefinition.unit_id)
                .where(ComponentProperty.component_id == second_id)
                .order_by(ComponentProperty.position)
            )
        ).all()
        assert [(row[0].value_text, row[0].value_number, row[2].symbol) for row in rows] == [
            ("4 МБ", Decimal(4096), "КБ"),
            ("5000 мВ", Decimal(5), "В"),
            ("16 МГц", Decimal(16), "МГц"),
            ("4 widgets", Decimal(4), "widgets"),
        ]

    for index, replacement, code, field in (
        (0, replace(converted[0], value_text="4 мс", unit="мс"), "incompatible_unit", "value_text"),
        (
            2,
            replace(converted[2], value_text="80 / 160 МГц", value_number=None, unit=None),
            "expected_numeric_value",
            "value_text",
        ),
        (
            0,
            replace(converted[0], label="Conflicting label"),
            "specification_definition_conflict",
            "label",
        ),
    ):
        async with database.sessions() as session:
            items = list(converted)
            items[index] = replacement
            with pytest.raises(CatalogValidationError) as raised:
                await DocumentSynchronization(session).synchronize(
                    second_id,
                    second_token,
                    replace(base, slug="diagnostic-second", specifications=tuple(items)),
                    (),
                    None,
                    actor_id,
                )
            await session.rollback()
            issues = cast(list[dict[str, object]], raised.value.details["issues"])
            assert issues[0]["path"] == [
                "specifications",
                index,
                field,
            ]
            assert issues[0]["code"] == code
            unchanged = await CatalogService(session).get_card(second_id)
            assert unchanged.edit_token == second_token
            assert unchanged.data.specifications[0].value_text == "4 МБ"

    async with database.sessions() as session:
        with pytest.raises(IntegrityError) as duplicate:
            await DocumentSynchronization(session).synchronize(
                second_id,
                second_token,
                replace(base, slug=first_slug, specifications=converted),
                (),
                None,
                actor_id,
            )
            await session.commit()
        await session.rollback()
        public = _error(duplicate.value)
        assert public.status_code == 422
        detail: object = public.detail
        assert isinstance(detail, dict)
        assert detail["issues"] == [{"path": ["slug"], "code": "slug_already_exists", "meta": {}}]


def test_editor_sync_disposable_postgresql(
    integration_settings: Settings, monkeypatch: MonkeyPatch
) -> None:
    base = make_url(integration_settings.database_url)
    name = f"ackb_editor_test_{uuid4().hex[:12]}"
    url = base.set(database=name).render_as_string(hide_password=False)
    asyncio.run(database_command(base, name))
    try:
        with monkeypatch.context() as environment:
            environment.setenv("ACKB_DATABASE_URL", url)
            command.upgrade(Config("alembic.ini"), "head")
        asyncio.run(exercise(integration_settings.model_copy(update={"database_url": url})))
    finally:
        asyncio.run(database_command(base, name, drop=True))
