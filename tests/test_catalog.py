"""Catalog validation, RBAC, and optimistic locking tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.catalog import DraftRequest, UpdateRequest, editor
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.catalog.domain import ComponentStatus, RevisionConflictError
from arduino_component_kb.catalog.models import Component
from arduino_component_kb.catalog.service import CatalogService


def principal(role: Role) -> Principal:
    return Principal(uuid4(), "user", "User", frozenset({role}), uuid4(), "hash", datetime.now(UTC))


async def test_workspace_rejects_student_on_backend() -> None:
    with pytest.raises(HTTPException) as error:
        await editor(principal(Role.STUDENT))
    assert error.value.status_code == 403
    assert await editor(principal(Role.TEACHER))


def test_draft_rejects_raw_html() -> None:
    with pytest.raises(ValidationError):
        DraftRequest(
            slug="sensor",
            title="Sensor",
            primary_category_id=uuid4(),
            summary="A sufficiently long summary",
            description="<script>unsafe</script>",
            difficulty="beginner",
            manual_original=True,
        )


def test_update_revision_is_not_part_of_draft_content() -> None:
    payload = UpdateRequest(
        slug="sensor",
        title="Sensor",
        primary_category_id=uuid4(),
        summary="A sufficiently long summary",
        description="Safe Markdown",
        difficulty="beginner",
        manual_original=True,
        revision=7,
    )
    assert payload.domain().slug == "sensor"
    assert payload.revision == 7


async def test_stale_revision_is_rejected_before_mutation() -> None:
    component = Mock(spec=Component)
    component.revision = 3
    session = Mock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=component)
    service = CatalogService(cast(AsyncSession, session))
    with pytest.raises(RevisionConflictError):
        await service.transition(uuid4(), 2, target=ComponentStatus.PUBLISHED, actor_id=uuid4())
