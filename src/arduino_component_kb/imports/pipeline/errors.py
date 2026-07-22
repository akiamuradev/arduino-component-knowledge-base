"""Typed and safely serializable import pipeline failures."""

from __future__ import annotations

import re
from enum import StrEnum

from arduino_component_kb.imports.pipeline.context import PipelineStage

_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


class ErrorCategory(StrEnum):
    ACQUISITION = "acquisition"
    PARSING = "parsing"
    NORMALIZATION = "normalization"
    IDENTITY = "identity"
    ENRICHMENT = "enrichment"
    QUALITY = "quality"
    COMPOSITION = "composition"
    PERSISTENCE = "persistence"


class ImportPipelineError(Exception):
    category: ErrorCategory
    stage: PipelineStage

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        if _ERROR_CODE.fullmatch(code) is None:
            raise ValueError("pipeline_error_code_invalid")
        self.code = code
        self.retryable = retryable
        super().__init__(code)

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "stage": self.stage.value,
            "code": self.code,
            "retryable": self.retryable,
        }


class AcquisitionError(ImportPipelineError):
    category = ErrorCategory.ACQUISITION
    stage = PipelineStage.ACQUISITION


class ParsingError(ImportPipelineError):
    category = ErrorCategory.PARSING
    stage = PipelineStage.EXTRACTION


class NormalizationError(ImportPipelineError):
    category = ErrorCategory.NORMALIZATION
    stage = PipelineStage.NORMALIZATION


class IdentityError(ImportPipelineError):
    category = ErrorCategory.IDENTITY
    stage = PipelineStage.IDENTITY


class EnrichmentError(ImportPipelineError):
    category = ErrorCategory.ENRICHMENT
    stage = PipelineStage.ENRICHMENT


class QualityError(ImportPipelineError):
    category = ErrorCategory.QUALITY
    stage = PipelineStage.EVALUATION


class CompositionError(ImportPipelineError):
    category = ErrorCategory.COMPOSITION
    stage = PipelineStage.COMPOSITION


class PersistenceError(ImportPipelineError):
    category = ErrorCategory.PERSISTENCE
    stage = PipelineStage.PERSISTENCE
