"""Real PostgreSQL transaction for the complete Stage 11 shadow pipeline."""

from __future__ import annotations

from sqlalchemy import func, select
from test_pipeline_orchestrator import request

from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.imports.persistence_models import (
    ImportPipelineArtifact,
    ImportReviewDraftRecord,
)
from arduino_component_kb.imports.pipeline import (
    EvidenceFirstImportOrchestrator,
    PipelineExecutionStatus,
    PostgresImportPersistenceGateway,
)


async def test_full_shadow_pipeline_is_idempotent_in_real_postgresql(
    integration_settings: Settings,
) -> None:
    database = Database(integration_settings)
    try:
        async with database.sessions() as session:
            transaction = await session.begin()
            orchestrator = EvidenceFirstImportOrchestrator(
                PostgresImportPersistenceGateway(session)
            )
            run_request = request()
            first = await orchestrator.run(run_request)
            second = await orchestrator.run(run_request)
            assert first.status is PipelineExecutionStatus.SUCCEEDED
            assert second.status is PipelineExecutionStatus.SUCCEEDED
            assert first.result is not None and second.result is not None
            assert first.result.persisted == second.result.persisted
            artifact_count = await session.scalar(
                select(func.count())
                .select_from(ImportPipelineArtifact)
                .where(ImportPipelineArtifact.id == first.result.persisted.artifact_id)
            )
            draft_count = await session.scalar(
                select(func.count())
                .select_from(ImportReviewDraftRecord)
                .where(ImportReviewDraftRecord.id == first.result.persisted.review_draft_id)
            )
            assert artifact_count == 1
            assert draft_count == 1
            await transaction.rollback()
    finally:
        await database.dispose()
