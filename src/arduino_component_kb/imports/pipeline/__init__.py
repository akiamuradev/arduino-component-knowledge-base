"""Parallel domain contracts for the future evidence-first import pipeline.

This package is intentionally not wired into the release 0.21 production flow.
"""

from arduino_component_kb.imports.pipeline.context import (
    PIPELINE_ORDER,
    ImportPipelineContext,
    PipelineStage,
    StageExecution,
    StageResult,
)
from arduino_component_kb.imports.pipeline.contracts import (
    CardComposer,
    EnrichmentProvider,
    FactExtractor,
    FactNormalizer,
    IdentityResolver,
    ImportPersistenceGateway,
    QualityEvaluator,
    SourceAcquirer,
)
from arduino_component_kb.imports.pipeline.errors import (
    AcquisitionError,
    CompositionError,
    EnrichmentError,
    ErrorCategory,
    IdentityError,
    ImportPipelineError,
    NormalizationError,
    ParsingError,
    PersistenceError,
    QualityError,
)
from arduino_component_kb.imports.pipeline.orchestration import (
    PipelineOrchestrator,
    PipelineStep,
)

__all__ = [
    "PIPELINE_ORDER",
    "AcquisitionError",
    "CardComposer",
    "CompositionError",
    "EnrichmentError",
    "EnrichmentProvider",
    "ErrorCategory",
    "FactExtractor",
    "FactNormalizer",
    "IdentityError",
    "IdentityResolver",
    "ImportPersistenceGateway",
    "ImportPipelineContext",
    "ImportPipelineError",
    "NormalizationError",
    "ParsingError",
    "PersistenceError",
    "PipelineOrchestrator",
    "PipelineStage",
    "PipelineStep",
    "QualityError",
    "QualityEvaluator",
    "SourceAcquirer",
    "StageExecution",
    "StageResult",
]
