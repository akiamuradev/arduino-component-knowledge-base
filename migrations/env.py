"""Alembic environment for the async PostgreSQL database."""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from arduino_component_kb.auth import models as auth_models
from arduino_component_kb.catalog import models as catalog_models
from arduino_component_kb.config import DatabaseSettings
from arduino_component_kb.db import Base
from arduino_component_kb.imports import models as import_models
from arduino_component_kb.media import models as media_models

config = context.config
registered_models = (
    auth_models.User,
    catalog_models.Component,
    import_models.ImportJob,
    media_models.MediaAsset,
)
target_metadata = Base.metadata


def database_url() -> str:
    """Load the migration URL through the same validated settings contract."""
    return DatabaseSettings().database_url


def run_migrations_offline() -> None:
    """Render SQL without opening a database connection."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations on a synchronous connection bridged by SQLAlchemy."""
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create a short-lived async engine exclusively for migrations."""
    section: dict[str, str] = {"sqlalchemy.url": database_url()}
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against PostgreSQL."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
