"""Catalog lifecycle transaction and audit coordination tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.catalog.domain import (
    COMPONENT_CHANGE_SUMMARIES,
    CatalogCard,
    CatalogValidationError,
    ComponentChangeAction,
    ComponentStatus,
)
from arduino_component_kb.catalog.models import ComponentRevision
from arduino_component_kb.catalog.operations import CatalogLifecycleOperations
from arduino_component_kb.catalog.service import CatalogService


async def test_lifecycle_operation_commits_revision_and_matching_audit_together() -> None:
    component_id = uuid4()
    actor_id = uuid4()
    card = Mock(spec=CatalogCard)
    card.id = component_id
    card.revision = 4
    revision = ComponentRevision(
        id=uuid4(),
        component_id=component_id,
        revision=4,
        status=ComponentStatus.APPROVED.value,
        previous_status=ComponentStatus.IN_REVIEW.value,
        action=ComponentChangeAction.APPROVED.value,
        change_summary=COMPONENT_CHANGE_SUMMARIES[ComponentChangeAction.APPROVED],
        content_json={},
        actor_id=actor_id,
        created_at=datetime.now(UTC),
    )
    session = Mock(spec=AsyncSession)
    session.flush = AsyncMock()
    session.scalar = AsyncMock(return_value=revision)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    catalog = Mock(spec=CatalogService)
    catalog.transition = AsyncMock(return_value=card)
    audit = Mock(spec=AuthRepository)
    audit.audit = AsyncMock()
    operations = CatalogLifecycleOperations(
        cast(AsyncSession, session),
        catalog=cast(CatalogService, catalog),
        audit=cast(AuthRepository, audit),
    )

    result = await operations.transition(
        component_id,
        3,
        ComponentStatus.APPROVED,
        actor_id,
        "request-lifecycle",
    )

    assert result is card
    catalog.transition.assert_awaited_once_with(
        component_id,
        3,
        ComponentStatus.APPROVED,
        actor_id,
    )
    audit_values = audit.audit.await_args.kwargs
    assert audit_values["actor_user_id"] == actor_id
    assert audit_values["action"] == ComponentChangeAction.APPROVED.value
    assert audit_values["object_type"] == "component"
    assert audit_values["object_id"] == component_id
    assert audit_values["request_id"] == "request-lifecycle"
    assert audit_values["outcome"] == "success"
    assert audit_values["details"] == {
        "revision": 4,
        "previous_status": ComponentStatus.IN_REVIEW.value,
        "status": ComponentStatus.APPROVED.value,
        "summary": "Карточка одобрена",
    }
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


async def test_lifecycle_operation_rolls_back_a_rejected_mutation() -> None:
    session = Mock(spec=AsyncSession)
    session.rollback = AsyncMock()
    session.commit = AsyncMock()
    catalog = Mock(spec=CatalogService)
    catalog.transition = AsyncMock(
        side_effect=CatalogValidationError("lifecycle_transition_denied")
    )
    audit = Mock(spec=AuthRepository)
    audit.audit = AsyncMock()
    operations = CatalogLifecycleOperations(
        cast(AsyncSession, session),
        catalog=cast(CatalogService, catalog),
        audit=cast(AuthRepository, audit),
    )

    with pytest.raises(CatalogValidationError):
        await operations.transition(
            uuid4(),
            1,
            ComponentStatus.PUBLISHED,
            uuid4(),
            "request-denied",
        )

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    audit.audit.assert_not_awaited()


async def test_lifecycle_operation_rolls_back_when_audit_write_fails() -> None:
    component_id = uuid4()
    actor_id = uuid4()
    card = Mock(spec=CatalogCard)
    card.id = component_id
    card.revision = 2
    revision = ComponentRevision(
        id=uuid4(),
        component_id=component_id,
        revision=2,
        status=ComponentStatus.IN_REVIEW.value,
        previous_status=ComponentStatus.DRAFT.value,
        action=ComponentChangeAction.SUBMITTED_FOR_REVIEW.value,
        change_summary=COMPONENT_CHANGE_SUMMARIES[ComponentChangeAction.SUBMITTED_FOR_REVIEW],
        content_json={},
        actor_id=actor_id,
        created_at=datetime.now(UTC),
    )
    session = Mock(spec=AsyncSession)
    session.flush = AsyncMock()
    session.scalar = AsyncMock(return_value=revision)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    catalog = Mock(spec=CatalogService)
    catalog.transition = AsyncMock(return_value=card)
    audit = Mock(spec=AuthRepository)
    audit.audit = AsyncMock(side_effect=RuntimeError("audit unavailable"))
    operations = CatalogLifecycleOperations(
        cast(AsyncSession, session),
        catalog=cast(CatalogService, catalog),
        audit=cast(AuthRepository, audit),
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await operations.transition(
            component_id,
            1,
            ComponentStatus.IN_REVIEW,
            actor_id,
            "request-audit-failure",
        )

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
