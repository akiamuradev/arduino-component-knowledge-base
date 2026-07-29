"""Teacher correction proposal domain and persistence contracts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.catalog import CorrectionProposalRequest
from arduino_component_kb.catalog.domain import (
    CatalogValidationError,
    ComponentNotFoundError,
    CorrectionProposalStatus,
)
from arduino_component_kb.catalog.models import ComponentCorrectionProposal
from arduino_component_kb.catalog.service import CatalogService


def test_correction_proposal_request_strips_and_bounds_message() -> None:
    payload = CorrectionProposalRequest(message="  Проверить напряжение питания.  ")
    assert payload.message == "Проверить напряжение питания."

    with pytest.raises(ValidationError):
        CorrectionProposalRequest(message="          ")


async def test_teacher_proposal_is_created_only_for_a_published_projection() -> None:
    component_id = uuid4()
    author_id = uuid4()
    session = Mock(spec=AsyncSession)
    session.scalar = AsyncMock(side_effect=[component_id, "Преподаватель"])
    session.flush = AsyncMock()

    proposal = await CatalogService(cast(AsyncSession, session)).propose_correction(
        component_id,
        "Проверить напряжение питания.",
        author_id,
    )

    assert proposal.component_id == component_id
    assert proposal.author_display_name == "Преподаватель"
    assert proposal.status is CorrectionProposalStatus.OPEN
    added = session.add.call_args.args[0]
    assert isinstance(added, ComponentCorrectionProposal)
    assert added.author_id == author_id
    assert added.message == "Проверить напряжение питания."
    session.flush.assert_awaited_once()


async def test_teacher_proposal_hides_unpublished_component() -> None:
    session = Mock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=None)

    with pytest.raises(ComponentNotFoundError):
        await CatalogService(cast(AsyncSession, session)).propose_correction(
            uuid4(),
            "Проверить напряжение питания.",
            uuid4(),
        )
    session.add.assert_not_called()


async def test_correction_proposal_can_be_resolved_only_once() -> None:
    component_id = uuid4()
    actor_id = uuid4()
    proposal_id = uuid4()
    component = SimpleNamespace(id=component_id, created_by=actor_id)
    row = SimpleNamespace(
        id=proposal_id,
        component_id=component_id,
        author_id=uuid4(),
        message="Проверить напряжение питания.",
        status=CorrectionProposalStatus.OPEN.value,
        created_at=SimpleNamespace(),
        resolved_by=None,
        resolved_at=None,
    )
    session = Mock(spec=AsyncSession)
    session.get = AsyncMock(return_value=component)
    session.scalar = AsyncMock(side_effect=[row, "Преподаватель"])
    session.flush = AsyncMock()
    service = CatalogService(cast(AsyncSession, session))

    resolved = await service.resolve_correction_proposal(
        component_id,
        proposal_id,
        CorrectionProposalStatus.APPLIED,
        actor_id,
        can_resolve_all=False,
    )

    assert resolved.status is CorrectionProposalStatus.APPLIED
    assert row.resolved_by == actor_id
    assert row.resolved_at is not None

    session.scalar = AsyncMock(return_value=row)
    with pytest.raises(CatalogValidationError, match="correction_proposal_resolved"):
        await service.resolve_correction_proposal(
            component_id,
            proposal_id,
            CorrectionProposalStatus.DISMISSED,
            actor_id,
            can_resolve_all=False,
        )
