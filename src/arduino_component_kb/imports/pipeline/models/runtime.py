"""Runtime requests, outcomes and failure states for the assembled import pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, PipelineStage
from arduino_component_kb.imports.pipeline.models.artifact import SourceArtifact
from arduino_component_kb.imports.pipeline.models.component_identity import ComponentIdentity
from arduino_component_kb.imports.pipeline.models.composition import ReviewDraft
from arduino_component_kb.imports.pipeline.models.enrichment import EnrichmentCandidate
from arduino_component_kb.imports.pipeline.models.extracted_facts import ExtractedFacts
from arduino_component_kb.imports.pipeline.models.kicad import KicadSymbolIndex
from arduino_component_kb.imports.pipeline.models.normalized_facts import NormalizedFacts
from arduino_component_kb.imports.pipeline.models.persistence import PersistedPipelineDraft
from arduino_component_kb.imports.pipeline.models.quality import QualityReport


class PipelineExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PipelineRunRequest:
    run_id: UUID
    source_id: UUID
    artifact: SourceArtifact
    kicad_index: KicadSymbolIndex
    pipeline_version: str = "2.0.0-shadow.1"
    component_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    context: ImportPipelineContext
    extracted_facts: ExtractedFacts
    normalized_facts: NormalizedFacts
    identity: ComponentIdentity
    enrichments: tuple[EnrichmentCandidate, ...]
    quality_report: QualityReport
    review_draft: ReviewDraft
    persisted: PersistedPipelineDraft
    duration_ms: float

    def __post_init__(self) -> None:
        if self.context.next_stage is not None:
            raise ValueError("pipeline_result_incomplete")
        if self.duration_ms < 0:
            raise ValueError("pipeline_result_duration_invalid")


@dataclass(frozen=True, slots=True)
class PipelineRunFailure:
    run_id: UUID
    stage: PipelineStage
    code: str
    retryable: bool
    attempts: int
    duration_ms: float
    error_type: str

    def __post_init__(self) -> None:
        if not self.code or len(self.code) > 80:
            raise ValueError("pipeline_failure_code_invalid")
        if not 1 <= self.attempts <= 10:
            raise ValueError("pipeline_failure_attempts_invalid")
        if self.duration_ms < 0:
            raise ValueError("pipeline_failure_duration_invalid")
        if not self.error_type or len(self.error_type) > 120:
            raise ValueError("pipeline_failure_error_type_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "stage": self.stage.value,
            "code": self.code,
            "retryable": self.retryable,
            "attempts": self.attempts,
            "duration_ms": self.duration_ms,
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class PipelineRunOutcome:
    status: PipelineExecutionStatus
    result: PipelineRunResult | None = None
    failure: PipelineRunFailure | None = None

    def __post_init__(self) -> None:
        succeeded = self.status is PipelineExecutionStatus.SUCCEEDED
        if succeeded != (self.result is not None) or succeeded == (self.failure is not None):
            raise ValueError("pipeline_outcome_state_invalid")


@dataclass(frozen=True, slots=True)
class OrchestratorPolicy:
    stage_timeouts_seconds: Mapping[PipelineStage, float]
    safe_retry_attempts: int = 2
    retry_delay_seconds: float = 0.05

    def __post_init__(self) -> None:
        if set(self.stage_timeouts_seconds) != set(PipelineStage):
            raise ValueError("pipeline_timeout_stages_invalid")
        if any(not 0.01 <= value <= 300 for value in self.stage_timeouts_seconds.values()):
            raise ValueError("pipeline_timeout_invalid")
        if not 1 <= self.safe_retry_attempts <= 5:
            raise ValueError("pipeline_retry_attempts_invalid")
        if not 0 <= self.retry_delay_seconds <= 5:
            raise ValueError("pipeline_retry_delay_invalid")
        object.__setattr__(
            self,
            "stage_timeouts_seconds",
            MappingProxyType(dict(self.stage_timeouts_seconds)),
        )

    @classmethod
    def uniform(
        cls,
        timeout_seconds: float = 15,
        *,
        safe_retry_attempts: int = 2,
        retry_delay_seconds: float = 0.05,
    ) -> OrchestratorPolicy:
        return cls(
            {stage: timeout_seconds for stage in PipelineStage},
            safe_retry_attempts,
            retry_delay_seconds,
        )
