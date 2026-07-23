"""Real PostgreSQL lifecycle, locking and audit checks for Stage 12."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_pipeline_orchestrator import request

from arduino_component_kb.auth.models import User
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.imports.persistence_models import (
    ComponentEnrichmentRecord,
    ComponentEnrichmentReviewRecord,
    ImportReviewActionRecord,
    ImportReviewStateRecord,
)
from arduino_component_kb.imports.pipeline import (
    EvidenceFirstImportOrchestrator,
    PipelineExecutionStatus,
    PostgresImportPersistenceGateway,
)
from arduino_component_kb.imports.pipeline.models.enrichment import ComponentSymbolRelationType
from arduino_component_kb.imports.pipeline.models.persistence import (
    EnrichmentReviewDecision,
)
from arduino_component_kb.imports.review import (
    ImportReviewConflictError,
    ImportReviewRepository,
)


async def test_review_actions_are_locked_audited_and_snapshot_safe(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            reviewer_id = uuid4()
            now = datetime.now(UTC)
            session.add(
                User(
                    id=reviewer_id,
                    login=f"stage12-{reviewer_id.hex}",
                    display_name="Stage 12 reviewer",
                    password_hash=f"integration-{reviewer_id.hex}",
                    status="active",
                    created_at=now,
                    updated_at=now,
                    last_login_at=None,
                )
            )
            outcome = await EvidenceFirstImportOrchestrator(
                PostgresImportPersistenceGateway(session)
            ).run(request("display_spi.md"))
            assert outcome.status is PipelineExecutionStatus.SUCCEEDED
            assert outcome.result is not None
            persisted = outcome.result.persisted
            assert len(persisted.enrichment_ids) == 1
            review_draft_id = persisted.review_draft_id
            enrichment_id = persisted.enrichment_ids[0]
            enrichment = await session.get(ComponentEnrichmentRecord, enrichment_id)
            assert enrichment is not None
            immutable_payload = dict(enrichment.payload)
            immutable_sha256 = enrichment.payload_sha256

            repository = ImportReviewRepository(session)
            revision = await repository.change_relation(
                review_draft_id=review_draft_id,
                enrichment_id=enrichment_id,
                reviewer_id=reviewer_id,
                relation_type=ComponentSymbolRelationType.ONBOARD_COMPONENT,
                reason="The symbol describes an onboard controller.",
                expected_revision=1,
                now=now,
            )
            assert revision == 2
            with pytest.raises(ImportReviewConflictError, match="import_review_revision_conflict"):
                await repository.review_enrichment(
                    review_draft_id=review_draft_id,
                    enrichment_id=enrichment_id,
                    reviewer_id=reviewer_id,
                    decision=EnrichmentReviewDecision.ACCEPT,
                    reason="Stale browser revision must not win.",
                    expected_revision=1,
                    now=now,
                )
            revision = await repository.review_enrichment(
                review_draft_id=review_draft_id,
                enrichment_id=enrichment_id,
                reviewer_id=reviewer_id,
                decision=EnrichmentReviewDecision.ACCEPT,
                reason="Evidence supports an onboard controller relation.",
                expected_revision=2,
                now=now,
            )
            revision = await repository.mark_parser_issue(
                review_draft_id=review_draft_id,
                code="parser.heading_noise",
                note="A decorative heading should be ignored in the next parser version.",
                reviewer_id=reviewer_id,
                expected_revision=revision,
                now=now,
            )
            revision = await repository.confirm(
                review_draft_id=review_draft_id,
                reviewer_id=reviewer_id,
                reason="Identity, relation and quality evidence were reviewed.",
                expected_revision=revision,
                now=now,
            )
            assert revision == 5

            state = await session.get(ImportReviewStateRecord, review_draft_id)
            updated = await session.get(ComponentEnrichmentRecord, enrichment_id)
            assert state is not None and state.status == "confirmed"
            assert state.confirmed_by == reviewer_id
            assert updated is not None
            assert updated.status == "accepted"
            assert updated.relation_type == "onboard_component"
            assert updated.payload == immutable_payload
            assert updated.payload_sha256 == immutable_sha256
            action_count = await session.scalar(
                select(func.count())
                .select_from(ImportReviewActionRecord)
                .where(ImportReviewActionRecord.review_draft_id == review_draft_id)
            )
            enrichment_review_count = await session.scalar(
                select(func.count())
                .select_from(ComponentEnrichmentReviewRecord)
                .where(ComponentEnrichmentReviewRecord.enrichment_id == enrichment_id)
            )
            assert action_count == 4
            assert enrichment_review_count == 1
            await transaction.rollback()
    finally:
        await database.dispose()
