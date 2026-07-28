"""Real PostgreSQL coverage for the ACKB 1.0.0 existing-user role backfill."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from pytest import MonkeyPatch
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

from arduino_component_kb.config import Settings

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _database_url(url: URL) -> str:
    return url.render_as_string(hide_password=False)


async def _create_database(base_url: URL, database_name: str) -> None:
    engine = create_async_engine(_database_url(base_url.set(database="postgres")))
    try:
        async with engine.connect() as raw_connection:
            connection = await raw_connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(text(f"CREATE DATABASE {database_name}"))
    finally:
        await engine.dispose()


async def _drop_database(base_url: URL, database_name: str) -> None:
    engine = create_async_engine(_database_url(base_url.set(database="postgres")))
    try:
        async with engine.connect() as raw_connection:
            connection = await raw_connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(text(f"DROP DATABASE {database_name} WITH (FORCE)"))
    finally:
        await engine.dispose()


def _upgrade(database_url: str, revision: str, monkeypatch: MonkeyPatch) -> None:
    with monkeypatch.context() as environment:
        environment.setenv("ACKB_DATABASE_URL", database_url)
        command.upgrade(Config(str(ROOT / "alembic.ini")), revision)


def _downgrade(database_url: str, revision: str, monkeypatch: MonkeyPatch) -> None:
    with monkeypatch.context() as environment:
        environment.setenv("ACKB_DATABASE_URL", database_url)
        command.downgrade(Config(str(ROOT / "alembic.ini")), revision)


async def _seed_revision_20_users(database_url: str) -> dict[str, UUID]:
    engine = create_async_engine(database_url)
    now = datetime.now(UTC)
    users = {
        "administrator": uuid4(),
        "teacher": uuid4(),
        "roleless": uuid4(),
        "active-editor": uuid4(),
        "expired-editor": uuid4(),
        "revoked-student": uuid4(),
        "disabled-roleless": uuid4(),
    }
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, display_name, password_hash, status,
                        created_at, updated_at, last_login_at
                    )
                    VALUES (
                        :id, :login, :display_name, :password_hash, :status,
                        :created_at, :updated_at, NULL
                    )
                    """
                ),
                [
                    {
                        "id": user_id,
                        "login": login,
                        "display_name": login,
                        "password_hash": "migration-test-password-hash",
                        "status": "disabled" if login == "disabled-roleless" else "active",
                        "created_at": now - timedelta(days=10),
                        "updated_at": now - timedelta(days=10),
                    }
                    for login, user_id in users.items()
                ],
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO user_roles (
                        id, user_id, role, granted_by, granted_at, expires_at, revoked_at
                    )
                    VALUES (
                        :id, :user_id, :role, NULL, :granted_at, :expires_at, :revoked_at
                    )
                    """
                ),
                [
                    {
                        "id": uuid4(),
                        "user_id": users["administrator"],
                        "role": "administrator",
                        "granted_at": now - timedelta(days=10),
                        "expires_at": None,
                        "revoked_at": None,
                    },
                    {
                        "id": uuid4(),
                        "user_id": users["teacher"],
                        "role": "teacher",
                        "granted_at": now - timedelta(days=10),
                        "expires_at": None,
                        "revoked_at": None,
                    },
                    {
                        "id": uuid4(),
                        "user_id": users["active-editor"],
                        "role": "editor",
                        "granted_at": now - timedelta(days=10),
                        "expires_at": now + timedelta(days=1),
                        "revoked_at": None,
                    },
                    {
                        "id": uuid4(),
                        "user_id": users["expired-editor"],
                        "role": "editor",
                        "granted_at": now - timedelta(days=10),
                        "expires_at": now - timedelta(days=1),
                        "revoked_at": None,
                    },
                    {
                        "id": uuid4(),
                        "user_id": users["revoked-student"],
                        "role": "student",
                        "granted_at": now - timedelta(days=10),
                        "expires_at": None,
                        "revoked_at": now - timedelta(days=1),
                    },
                ],
            )
    finally:
        await engine.dispose()
    return users


async def _role_state(database_url: str) -> dict[str, tuple[list[str], set[str]]]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            users.login,
                            user_roles.role,
                            (
                                user_roles.revoked_at IS NULL
                                AND (
                                    user_roles.expires_at IS NULL
                                    OR user_roles.expires_at > CURRENT_TIMESTAMP
                                )
                            ) AS effective
                        FROM users
                        LEFT JOIN user_roles ON user_roles.user_id = users.id
                        ORDER BY users.login, user_roles.granted_at, user_roles.id
                        """
                    )
                )
            ).mappings()
            state: dict[str, tuple[list[str], set[str]]] = {}
            for row in rows:
                login = str(row["login"])
                history, effective = state.setdefault(login, ([], set()))
                if row["role"] is not None:
                    role = str(row["role"])
                    history.append(role)
                    if bool(row["effective"]):
                        effective.add(role)
            return state
    finally:
        await engine.dispose()


async def _revision(database_url: str) -> str:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            value = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            return str(value)
    finally:
        await engine.dispose()


def test_existing_users_receive_only_safe_missing_role_backfill(
    integration_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    base_url = make_url(integration_settings.database_url)
    database_name = f"ackb_role_migration_{uuid4().hex[:12]}"
    database_url = _database_url(base_url.set(database=database_name))
    asyncio.run(_create_database(base_url, database_name))
    try:
        _upgrade(database_url, "20260728_20", monkeypatch)
        asyncio.run(_seed_revision_20_users(database_url))

        _upgrade(database_url, "head", monkeypatch)
        assert asyncio.run(_revision(database_url)) == "20260728_23"
        migrated = asyncio.run(_role_state(database_url))

        assert migrated["administrator"] == (["administrator"], {"administrator"})
        assert migrated["teacher"] == (["teacher"], {"teacher"})
        assert migrated["roleless"] == (["student"], {"student"})
        assert migrated["disabled-roleless"] == (["student"], {"student"})
        assert migrated["active-editor"] == (["editor", "student"], {"editor", "student"})
        assert migrated["expired-editor"] == (["editor", "student"], {"student"})
        assert migrated["revoked-student"] == (["student", "student"], {"student"})

        _downgrade(database_url, "20260728_20", monkeypatch)
        assert asyncio.run(_revision(database_url)) == "20260728_20"
        downgraded = asyncio.run(_role_state(database_url))

        assert downgraded["administrator"] == (["administrator"], {"administrator"})
        assert downgraded["teacher"] == (["teacher"], {"teacher"})
        assert downgraded["roleless"] == ([], set())
        assert downgraded["disabled-roleless"] == ([], set())
        assert downgraded["active-editor"] == (["editor"], {"editor"})
        assert downgraded["expired-editor"] == (["editor"], set())
        assert downgraded["revoked-student"] == (["student"], set())
    finally:
        asyncio.run(_drop_database(base_url, database_name))
