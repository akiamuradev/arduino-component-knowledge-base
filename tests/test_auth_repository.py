"""Regression tests for authentication repository SQL statements."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from arduino_component_kb.auth.repository import AuthRepository


async def test_active_administrator_query_has_an_explicit_join_path() -> None:
    session = Mock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=[])
    repository = AuthRepository(cast(AsyncSession, session))

    assert await repository.count_active_administrators() == 0

    call = session.scalars.await_args
    assert call is not None
    statement = cast(Select[tuple[UUID]], call.args[0])
    sql = str(statement)
    assert "FROM users JOIN user_roles ON user_roles.user_id = users.id" in sql
    assert "FOR UPDATE" in sql


async def test_administrator_changes_use_a_transaction_advisory_lock() -> None:
    session = Mock(spec=AsyncSession)
    session.execute = AsyncMock()
    repository = AuthRepository(cast(AsyncSession, session))

    await repository.lock_administrator_membership()

    call = session.execute.await_args
    assert call is not None
    assert "pg_advisory_xact_lock" in str(call.args[0])


async def test_role_lookup_filters_revoked_and_expired_grants() -> None:
    session = Mock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=["student"])
    repository = AuthRepository(cast(AsyncSession, session))

    roles = await repository._roles(UUID(int=1), datetime.now(UTC))

    assert {role.value for role in roles} == {"student"}
    call = session.scalars.await_args
    assert call is not None
    sql = str(call.args[0])
    assert "user_roles.revoked_at IS NULL" in sql
    assert "user_roles.expires_at IS NULL OR user_roles.expires_at >" in sql
