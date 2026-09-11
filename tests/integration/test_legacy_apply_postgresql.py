"""Legacy apply acceptance in a newly created database, never the operator catalog."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4
from zipfile import ZipFile

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

from arduino_component_kb.api.legacy_imports import (
    ApplyInput,
    DecisionInput,
    apply_bundle,
    bundle_items,
    decide,
    retry_bundle,
)
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.catalog.models import Component
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.catalog.synchronization import DocumentSynchronization
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.legacy.models import LegacyBundle
from arduino_component_kb.legacy.parser import Analysis, Target, digest
from arduino_component_kb.legacy.planning import review_hash
from arduino_component_kb.legacy.processor import apply_item, save_analysis
from arduino_component_kb.media.storage import MediaStorage


async def database_command(base: URL, name: str, *, drop: bool = False) -> None:
    assert name.startswith("ackb_legacy_test_") and name.replace("_", "").isalnum()
    engine = create_async_engine(base.set(database="postgres"))
    try:
        async with engine.connect() as raw:
            connection = await raw.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(
                text(
                    f'DROP DATABASE "{name}" WITH (FORCE)' if drop else f'CREATE DATABASE "{name}"'
                )
            )
    finally:
        await engine.dispose()


async def exercise(settings: Settings, empty_archive: Path) -> None:
    database = Database(settings)
    storage = cast(MediaStorage, AsyncMock(spec=MediaStorage))
    try:
        async with database.sessions() as session:
            now = datetime.now(UTC)
            user = await AuthRepository(session).create_user(
                login="legacy-admin",
                display_name="Legacy test",
                password_hash="fixture-only",  # noqa: S106 -- isolated test, no login
                roles=frozenset({Role.ADMINISTRATOR}),
                actor_id=None,
                now=now,
            )
            principal = Principal(
                user_id=user.id,
                login=user.login,
                display_name=user.display_name,
                roles=frozenset({Role.ADMINISTRATOR}),
                session_id=uuid4(),
                csrf_hash="fixture",
                expires_at=now + timedelta(hours=1),
            )
            target = Target(identity=digest("first"), title="DHT11", category="ДАТЧИКИ", rows=[116])

            async def planned(value: Target) -> LegacyBundle:
                bundle = LegacyBundle(
                    id=uuid4(),
                    owner_id=user.id,
                    status="analyzing",
                    zip_size=1,
                    xlsx_size=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(bundle)
                await session.flush()
                await save_analysis(
                    session,
                    bundle,
                    Analysis(
                        zip_sha256="a" * 64,
                        xlsx_sha256="b" * 64,
                        targets=[value],
                        statistics={},
                        warnings=[],
                    ),
                )
                await session.commit()
                return bundle

            first = await planned(target)
            second = await planned(target)
            items = await bundle_items(session, first.id)
            assert first.plan_hash == second.plan_hash
            assert review_hash(first, items) == review_hash(
                second, await bundle_items(session, second.id)
            )
            assert await session.scalar(select(func.count()).select_from(Component)) == 0
            assert items[0].decision == "create"
            with pytest.raises(HTTPException) as stale:
                await apply_bundle(
                    first.id,
                    ApplyInput(plan_hash="0" * 64, confirmation="ИМПОРТ"),
                    principal,
                    principal,
                    session,
                )
            assert stale.value.status_code == 409
            await apply_bundle(
                first.id,
                ApplyInput(plan_hash=review_hash(first, items), confirmation="ИМПОРТ"),
                principal,
                principal,
                session,
            )
            assert first.confirmed_by == user.id
            await apply_item(
                session, first, items[0], storage, settings, empty_archive, empty_archive
            )
            await session.commit()
            component_id = items[0].result_id
            assert component_id is not None and items[0].status == "applied"
            card = await CatalogService(session).get_card(component_id)
            assert card.status.value == "draft" and card.has_legacy_provenance
            assert card.published_at is None

            repeated = (await bundle_items(session, second.id))[0]
            second.confirmed_by = user.id
            await apply_item(
                session, second, repeated, storage, settings, empty_archive, empty_archive
            )
            await session.commit()
            assert repeated.status == "skipped" and repeated.result_id == component_id
            assert await session.scalar(select(func.count()).select_from(Component)) == 1

            merge = await planned(
                target.model_copy(
                    update={"identity": digest("additional"), "description": "Imported text"}
                )
            )
            merge_items = await bundle_items(session, merge.id)
            selected = merge_items[0]
            assert selected.decision == "review"
            await decide(
                merge.id,
                selected.id,
                DecisionInput(
                    plan_hash=review_hash(merge, merge_items),
                    decision="merge",
                    merge_id=component_id,
                ),
                principal,
                principal,
                session,
            )
            old_revision = card.revision
            card = await DocumentSynchronization(session).synchronize(
                component_id,
                card.edit_token,
                replace(card.data, description="Manual edit must survive"),
                (),
                None,
                user.id,
            )
            await session.commit()
            assert card.revision == old_revision
            await apply_bundle(
                merge.id,
                ApplyInput(plan_hash=review_hash(merge, merge_items), confirmation="ИМПОРТ"),
                principal,
                principal,
                session,
            )
            await apply_item(
                session, merge, selected, storage, settings, empty_archive, empty_archive
            )
            await session.commit()
            assert selected.status == "needs_review"
            assert (
                await CatalogService(session).get_card(component_id)
            ).data.description == "Manual edit must survive"

            # A failed item in a completed batch can retry; applied siblings stay untouched.
            first.status = "completed"
            items[0].status = "failed"
            await session.commit()
            await retry_bundle(first.id, principal, principal, session)
            assert items[0].status == "planned" and first.status == "applying"
            await apply_item(
                session, first, items[0], storage, settings, empty_archive, empty_archive
            )
            await session.commit()
            assert items[0].status == "skipped"
            assert await session.scalar(select(func.count()).select_from(Component)) == 1
    finally:
        await database.dispose()


def test_legacy_disposable_postgresql(
    integration_settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = make_url(integration_settings.database_url)
    name = f"ackb_legacy_test_{uuid4().hex[:12]}"
    url = base.set(database=name).render_as_string(hide_password=False)
    empty_archive = tmp_path / "empty.zip"
    with ZipFile(empty_archive, "w"):
        pass
    asyncio.run(database_command(base, name))
    try:
        with monkeypatch.context() as environment:
            environment.setenv("ACKB_DATABASE_URL", url)
            command.upgrade(Config("alembic.ini"), "head")
        asyncio.run(
            exercise(integration_settings.model_copy(update={"database_url": url}), empty_archive)
        )
        with monkeypatch.context() as environment:
            environment.setenv("ACKB_DATABASE_URL", url)
            command.downgrade(Config("alembic.ini"), "20260910_30")
            command.upgrade(Config("alembic.ini"), "head")
    finally:
        asyncio.run(database_command(base, name, drop=True))
