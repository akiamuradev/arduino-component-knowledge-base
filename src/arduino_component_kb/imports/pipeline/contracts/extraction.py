"""Fact extraction boundary."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, StageResult

ArtifactT_contra = TypeVar("ArtifactT_contra", contravariant=True)
FactsT_co = TypeVar("FactsT_co", covariant=True)


@runtime_checkable
class FactExtractor(Protocol[ArtifactT_contra, FactsT_co]):
    async def extract(
        self, context: ImportPipelineContext, artifact: ArtifactT_contra
    ) -> StageResult[FactsT_co]: ...
