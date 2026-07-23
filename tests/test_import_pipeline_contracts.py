"""Contracts for the parallel, not-yet-wired import pipeline domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from arduino_component_kb.imports.pipeline import (
    PIPELINE_ORDER,
    AcquisitionError,
    CardComposer,
    CompositionError,
    EnrichmentError,
    EnrichmentProvider,
    FactExtractor,
    FactNormalizer,
    IdentityError,
    IdentityResolver,
    ImportPersistenceGateway,
    ImportPipelineContext,
    ImportPipelineError,
    NormalizationError,
    ParsingError,
    PersistenceError,
    PipelineOrchestrator,
    PipelineStage,
    QualityError,
    QualityEvaluator,
    SourceAcquirer,
    StageExecution,
    StageResult,
)

STARTED_AT = datetime(2026, 7, 23, 9, 0, tzinfo=UTC)
RUN_ID = UUID("00000000-0000-4000-8000-000000000001")


def context() -> ImportPipelineContext:
    return ImportPipelineContext(
        run_id=RUN_ID,
        source_key="seeed_wiki",
        source_locator="sites/en/docs/Sensor/example.md",
        pipeline_version="imports-v2",
        started_at=STARTED_AT,
    )


def result_for(
    current: ImportPipelineContext, stage: PipelineStage, value: str
) -> StageResult[str]:
    offset = len(current.executions)
    started_at = STARTED_AT + timedelta(seconds=offset * 2)
    updated = current.advance(
        StageExecution(
            stage=stage,
            started_at=started_at,
            completed_at=started_at + timedelta(seconds=1),
        )
    )
    return StageResult(stage=stage, context=updated, value=value)


class ContractImplementation:
    async def acquire(self, current: ImportPipelineContext, request: str) -> StageResult[str]:
        return result_for(current, PipelineStage.ACQUISITION, request)

    async def extract(self, current: ImportPipelineContext, artifact: str) -> StageResult[str]:
        return result_for(current, PipelineStage.EXTRACTION, artifact)

    async def normalize(self, current: ImportPipelineContext, facts: str) -> StageResult[str]:
        return result_for(current, PipelineStage.NORMALIZATION, facts)

    async def resolve(self, current: ImportPipelineContext, facts: str) -> StageResult[str]:
        return result_for(current, PipelineStage.IDENTITY, facts)

    async def enrich(self, current: ImportPipelineContext, value: str) -> StageResult[str]:
        return result_for(current, PipelineStage.ENRICHMENT, value)

    async def evaluate(self, current: ImportPipelineContext, value: str) -> StageResult[str]:
        return result_for(current, PipelineStage.EVALUATION, value)

    async def compose(self, current: ImportPipelineContext, value: str) -> StageResult[str]:
        return result_for(current, PipelineStage.COMPOSITION, value)

    async def persist(self, current: ImportPipelineContext, draft: str) -> StageResult[str]:
        return result_for(current, PipelineStage.PERSISTENCE, draft)


def test_stage_protocols_are_structural_and_runtime_checkable() -> None:
    implementation = ContractImplementation()
    acquirer: SourceAcquirer[str, str] = implementation
    extractor: FactExtractor[str, str] = implementation
    normalizer: FactNormalizer[str, str] = implementation
    resolver: IdentityResolver[str, str] = implementation
    enricher: EnrichmentProvider[str, str] = implementation
    evaluator: QualityEvaluator[str, str] = implementation
    composer: CardComposer[str, str] = implementation
    persistence: ImportPersistenceGateway[str, str] = implementation

    contracts: tuple[object, ...] = (
        acquirer,
        extractor,
        normalizer,
        resolver,
        enricher,
        evaluator,
        composer,
        persistence,
    )
    protocol_types = (
        SourceAcquirer,
        FactExtractor,
        FactNormalizer,
        IdentityResolver,
        EnrichmentProvider,
        QualityEvaluator,
        CardComposer,
        ImportPersistenceGateway,
    )
    assert all(
        isinstance(value, protocol)
        for value, protocol in zip(contracts, protocol_types, strict=True)
    )


def test_pipeline_context_has_stable_json_round_trip() -> None:
    current = context()
    current = result_for(current, PipelineStage.ACQUISITION, "artifact").context
    extraction_started = STARTED_AT + timedelta(seconds=2)
    current = current.advance(
        StageExecution(
            stage=PipelineStage.EXTRACTION,
            started_at=extraction_started,
            completed_at=extraction_started + timedelta(seconds=1),
            warnings=("section_missing",),
        )
    )

    encoded = current.to_json()

    assert encoded == current.to_json()
    assert ImportPipelineContext.from_json(encoded) == current
    assert current.next_stage is PipelineStage.NORMALIZATION


@pytest.mark.parametrize(
    ("error_type", "category", "stage"),
    [
        (AcquisitionError, "acquisition", "acquisition"),
        (ParsingError, "parsing", "extraction"),
        (NormalizationError, "normalization", "normalization"),
        (IdentityError, "identity", "identity"),
        (EnrichmentError, "enrichment", "enrichment"),
        (QualityError, "quality", "evaluation"),
        (CompositionError, "composition", "composition"),
        (PersistenceError, "persistence", "persistence"),
    ],
)
def test_pipeline_errors_have_safe_categories(
    error_type: type[ImportPipelineError], category: str, stage: str
) -> None:
    error = error_type("source_rejected", retryable=error_type is AcquisitionError)

    assert error.as_dict() == {
        "category": category,
        "stage": stage,
        "code": "source_rejected",
        "retryable": error_type is AcquisitionError,
    }
    assert str(error) == "source_rejected"


@dataclass(frozen=True, slots=True)
class RecordingStep:
    stage: PipelineStage

    async def run(self, current: ImportPipelineContext) -> ImportPipelineContext:
        return result_for(current, self.stage, self.stage.value).context


async def test_orchestration_stub_runs_each_stage_once_in_order() -> None:
    orchestrator = PipelineOrchestrator(tuple(RecordingStep(stage) for stage in PIPELINE_ORDER))

    completed = await orchestrator.run(context())

    assert tuple(execution.stage for execution in completed.executions) == PIPELINE_ORDER
    assert completed.next_stage is None


def test_orchestration_stub_rejects_an_incomplete_or_reordered_pipeline() -> None:
    with pytest.raises(ValueError, match="pipeline_definition_order_invalid"):
        PipelineOrchestrator((RecordingStep(PipelineStage.EXTRACTION),))


def test_stage_11_pipeline_is_wired_only_to_shadow_worker_bridge_and_cli() -> None:
    imports_root = (
        Path(__file__).parents[1] / "src" / "arduino_component_kb" / "imports"
    ).resolve()
    pipeline_root = (imports_root / "pipeline").resolve()
    production_files = (
        path for path in imports_root.rglob("*.py") if not path.is_relative_to(pipeline_root)
    )
    references = {
        path.relative_to(imports_root).as_posix()
        for path in production_files
        if "arduino_component_kb.imports.pipeline" in path.read_text(encoding="utf-8")
    }
    assert references == {"processor.py", "shadow_dry_run.py"}
    processor = (imports_root / "processor.py").read_text(encoding="utf-8")
    assert "settings.import_pipeline_shadow_enabled" in processor
    assert "run_repository_shadow" in processor
    assert "persist_repository_draft" in processor


def test_context_deserialization_rejects_untyped_payload() -> None:
    with pytest.raises(ValueError, match="pipeline_context_payload_invalid"):
        ImportPipelineContext.from_dict(cast(dict[str, object], {"run_id": 123}))
