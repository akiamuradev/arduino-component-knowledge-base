"""Real PostgreSQL transaction for the complete Stage 11 shadow pipeline."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from test_pipeline_orchestrator import request
from test_shadow_import import legacy

from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.imports.acquisition import AcquiredEntry
from arduino_component_kb.imports.models import ImportJob, Source
from arduino_component_kb.imports.persistence_models import (
    ImportPipelineArtifact,
    ImportReviewDraftRecord,
)
from arduino_component_kb.imports.pipeline import (
    EvidenceFirstImportOrchestrator,
    PipelineExecutionStatus,
    PostgresImportPersistenceGateway,
    worker_shadow,
)
from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, StageResult
from arduino_component_kb.imports.pipeline.errors import PersistenceError
from arduino_component_kb.imports.pipeline.models import (
    PersistedPipelineDraft,
    PipelinePersistenceInput,
)
from arduino_component_kb.imports.repository_domain import RepositorySnapshot


class SqlFailureAfterPersistence(PostgresImportPersistenceGateway):
    failure_mode = "sql"

    async def persist(
        self, context: ImportPipelineContext, value: PipelinePersistenceInput
    ) -> StageResult[PersistedPipelineDraft]:
        result = await super().persist(context, value)
        if self.failure_mode == "success":
            return result
        if self.failure_mode == "logical":
            raise PersistenceError("persistence_payload_invalid")
        if self.failure_mode == "flush":
            self.session.add(ImportPipelineArtifact())
            await self.session.flush()
        # PostgreSQL marks the transaction aborted; the orchestrator returns FAILED.
        await self.session.execute(text("SELECT 1 / 0"))
        raise AssertionError("SQL failure was not raised")


@pytest.mark.parametrize("failure_mode", ["sql", "flush", "logical", "success"])
async def test_worker_shadow_preserves_outer_transaction(
    integration_settings: Settings, monkeypatch: pytest.MonkeyPatch, failure_mode: str
) -> None:
    monkeypatch.setattr(SqlFailureAfterPersistence, "failure_mode", failure_mode)
    run_request = request()
    monkeypatch.setattr(
        worker_shadow, "PostgresImportPersistenceGateway", SqlFailureAfterPersistence
    )
    monkeypatch.setattr(
        worker_shadow._kicad_index_loader,
        "load",
        Mock(
            return_value=SimpleNamespace(
                index=run_request.kicad_index,
                manifest=SimpleNamespace(source_revision="b" * 40, index_sha256="c" * 64),
            )
        ),
    )
    settings = integration_settings.model_copy(
        update={
            "kicad_index_expected_revision": "b" * 40,
            "kicad_index_expected_sha256": "c" * 64,
        }
    )
    parsed = await legacy("complete.md")
    snapshot = RepositorySnapshot(
        parsed.repository_url,
        parsed.source_revision,
        {"complete.md": run_request.artifact.content},
    )
    database = Database(settings)
    try:
        async with database.sessions() as session:
            async with session.begin():
                await session.execute(text("CREATE TEMP TABLE shadow_outer_marker (value int)"))
                await session.execute(text("INSERT INTO shadow_outer_marker VALUES (1)"))
                report = await worker_shadow.run_repository_shadow(
                    session,
                    settings,
                    ImportJob(id=uuid4()),
                    Source(id=run_request.source_id, key="seeed_wiki"),
                    AcquiredEntry(snapshot, "complete.md", len(run_request.artifact.content)),
                    parsed,
                )
                expected_rows = 1 if failure_mode == "success" else 0
                assert report.pipeline_status == ("succeeded" if expected_rows else "failed")
                if not expected_rows:
                    assert report.failure is not None
                    assert report.failure["stage"] == "persistence"
                # A legacy write after the shadow call must still be possible.
                await session.execute(text("INSERT INTO shadow_outer_marker VALUES (2)"))
                assert await session.scalar(text("SELECT count(*) FROM shadow_outer_marker")) == 2
                assert (
                    await session.scalar(select(func.count()).select_from(ImportPipelineArtifact))
                    == expected_rows
                )
                assert (
                    await session.scalar(select(func.count()).select_from(ImportReviewDraftRecord))
                    == expected_rows
                )
                if expected_rows:
                    await session.rollback()
    finally:
        await database.dispose()


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
