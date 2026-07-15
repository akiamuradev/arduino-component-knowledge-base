"""Async SQLAlchemy infrastructure without runtime schema creation."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from arduino_component_kb.config import Settings


class Base(DeclarativeBase):
    """Declarative metadata consumed by Alembic only."""


class DatabaseGateway(Protocol):
    """Minimal database lifecycle required by the HTTP application."""

    async def ping(self) -> None:
        """Raise when PostgreSQL cannot execute a trivial query."""

    async def dispose(self) -> None:
        """Release owned connection-pool resources."""


class Database:
    """Own the async engine and session factory."""

    def __init__(self, settings: Settings) -> None:
        connect_args = {"timeout": settings.database_connect_timeout_seconds}
        self.engine: AsyncEngine = create_async_engine(
            settings.database_url,
            echo=settings.database_echo,
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            connect_args=connect_args,
        )
        self.sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

    async def ping(self) -> None:
        """Verify that PostgreSQL accepts a connection and SELECT 1."""
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        """Close the engine pool."""
        await self.engine.dispose()
