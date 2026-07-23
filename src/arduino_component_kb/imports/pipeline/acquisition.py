"""Acquisition adapter for already fetched, policy-checked source artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from arduino_component_kb.imports.pipeline.context import (
    ImportPipelineContext,
    PipelineStage,
    StageExecution,
    StageResult,
)
from arduino_component_kb.imports.pipeline.errors import AcquisitionError
from arduino_component_kb.imports.pipeline.models import SourceArtifact


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class PreparedSourceAcquirer:
    """Record acquisition after the outer allowlisted fetcher has supplied immutable bytes."""

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()

    async def acquire(
        self, context: ImportPipelineContext, artifact: SourceArtifact
    ) -> StageResult[SourceArtifact]:
        started_at = self.clock.now()
        if context.next_stage is not PipelineStage.ACQUISITION:
            raise AcquisitionError("acquisition_stage_out_of_order")
        if context.source_key != artifact.metadata.source.source_key:
            raise AcquisitionError("pipeline_source_mismatch")
        completed_at = self.clock.now()
        updated = context.advance(
            StageExecution(PipelineStage.ACQUISITION, started_at, completed_at)
        )
        return StageResult(PipelineStage.ACQUISITION, updated, artifact)
