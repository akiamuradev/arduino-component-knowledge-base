"""Non-writing persistence boundary for batch shadow evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from arduino_component_kb.imports.pipeline.context import (
    ImportPipelineContext,
    PipelineStage,
    StageExecution,
    StageResult,
)
from arduino_component_kb.imports.pipeline.errors import PersistenceError
from arduino_component_kb.imports.pipeline.models import (
    PersistedPipelineDraft,
    PipelinePersistenceInput,
)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class DryRunPersistenceGateway:
    """Exercise the full persistence contract while returning deterministic IDs only."""

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()

    async def persist(
        self, context: ImportPipelineContext, value: PipelinePersistenceInput
    ) -> StageResult[PersistedPipelineDraft]:
        started_at = self.clock.now()
        if context.next_stage is not PipelineStage.PERSISTENCE:
            raise PersistenceError("persistence_stage_out_of_order")
        if context.source_key != value.draft.artifact.source.source_key:
            raise PersistenceError("pipeline_source_mismatch")
        enrichment_ids = tuple(
            value.enrichment_id(
                candidate.relation.symbol.record_id,
                candidate.relation.symbol.source_revision,
                candidate.relation.relation_type.value,
            )
            for candidate in value.composition.enrichments
        )
        persisted = PersistedPipelineDraft(
            value.artifact_id,
            value.identity_id,
            value.evaluation_id,
            value.review_draft_id,
            enrichment_ids,
        )
        completed_at = self.clock.now()
        updated = context.advance(
            StageExecution(PipelineStage.PERSISTENCE, started_at, completed_at)
        )
        return StageResult(PipelineStage.PERSISTENCE, updated, persisted)
