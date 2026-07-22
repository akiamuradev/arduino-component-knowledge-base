"""Semantic normalization boundary."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, StageResult

FactsT_contra = TypeVar("FactsT_contra", contravariant=True)
NormalizedT_co = TypeVar("NormalizedT_co", covariant=True)


@runtime_checkable
class FactNormalizer(Protocol[FactsT_contra, NormalizedT_co]):
    async def normalize(
        self, context: ImportPipelineContext, facts: FactsT_contra
    ) -> StageResult[NormalizedT_co]: ...
