"""Real PostgreSQL lifecycle for teacher correction proposals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func

from arduino_component_kb.auth.models import User
from arduino_component_kb.catalog.domain import (
    CatalogValidationError,
    ComponentNotFoundError,
    CorrectionProposalStatus,
    Difficulty,
    DraftData,
)
from arduino_component_kb.catalog.models import Category, PublishedSearchDocument
from arduino_component_kb.catalog.service import CatalogService
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database

pytestmark = pytest.mark.integration


def _draft(category_id: UUID, suffix: str) -> DraftData:
    return DraftData(
        slug=f"correction-proposal-{suffix}",
        title="Correction proposal component",
        aliases=(),
        manufacturer=None,
        model=None,
        primary_category_id=category_id,
        tags=(),
        summary="A published projection used to test correction proposals.",
        description="A sufficiently detailed component description.",
        purpose=None,
        usage_notes=None,
        safety_notes=None,
        difficulty=Difficulty.BEGINNER,
        teacher_notes=None,
        manual_original=True,
    )


async def test_correction_proposal_lifecycle_is_separate_from_component_revision(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            now = datetime.now(UTC)
            suffix = uuid4().hex
            editor_id = uuid4()
            teacher_id = uuid4()
            outsider_id = uuid4()
            category_id = uuid4()
            session.add_all(
                [
                    User(
                        id=user_id,
                        login=f"correction-{label}-{suffix}",
                        display_name=display_name,
                        password_hash=f"integration-{suffix}",
                        status="active",
                        created_at=now,
                        updated_at=now,
                        last_login_at=None,
                    )
                    for user_id, label, display_name in (
                        (editor_id, "editor", "Редактор"),
                        (teacher_id, "teacher", "Преподаватель"),
                        (outsider_id, "outsider", "Другой редактор"),
                    )
                ]
            )
            session.add(
                Category(
                    id=category_id,
                    key=f"correction-{suffix}",
                    name="Correction proposals",
                    description=None,
                    parent_id=None,
                    position=9001,
                    is_active=True,
                )
            )
            await session.flush()
            service = CatalogService(session)
            card = await service.create(_draft(category_id, suffix), editor_id)
            original_revision = card.revision
            session.add(
                PublishedSearchDocument(
                    component_id=card.id,
                    revision=card.revision,
                    category_id=category_id,
                    difficulty=Difficulty.BEGINNER.value,
                    title=card.data.title,
                    aliases_text="",
                    manufacturer="",
                    model="",
                    summary=card.data.summary,
                    tags_text="",
                    search_text=f"{card.data.title} {card.data.summary}",
                    search_vector=cast(
                        str,
                        func.to_tsvector(
                            "simple",
                            f"{card.data.title} {card.data.summary}",
                        ),
                    ),
                    published_at=now,
                )
            )
            await session.flush()

            proposal = await service.propose_correction(
                card.id,
                "Уточнить допустимое напряжение питания.",
                teacher_id,
            )
            assert proposal.status is CorrectionProposalStatus.OPEN
            assert card.revision == original_revision

            listed = await service.correction_proposals(
                card.id,
                editor_id,
                can_view_all=False,
            )
            assert [item.id for item in listed] == [proposal.id]

            with pytest.raises(ComponentNotFoundError):
                await service.correction_proposals(
                    card.id,
                    outsider_id,
                    can_view_all=False,
                )

            resolved = await service.resolve_correction_proposal(
                card.id,
                proposal.id,
                CorrectionProposalStatus.APPLIED,
                editor_id,
                can_resolve_all=False,
            )
            assert resolved.status is CorrectionProposalStatus.APPLIED
            assert card.revision == original_revision

            with pytest.raises(CatalogValidationError, match="correction_proposal_resolved"):
                await service.resolve_correction_proposal(
                    card.id,
                    proposal.id,
                    CorrectionProposalStatus.DISMISSED,
                    editor_id,
                    can_resolve_all=False,
                )
            await transaction.rollback()
    finally:
        await database.dispose()
