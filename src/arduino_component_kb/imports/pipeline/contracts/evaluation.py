"""Import quality evaluation boundary."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, StageResult

EvaluationInputT_contra = TypeVar("EvaluationInputT_contra", contravariant=True)
QualityT_co = TypeVar("QualityT_co", covariant=True)


@runtime_checkable
class QualityEvaluator(Protocol[EvaluationInputT_contra, QualityT_co]):
    async def evaluate(
        self, context: ImportPipelineContext, value: EvaluationInputT_contra
    ) -> StageResult[QualityT_co]: ...
