"""External enrichment boundary."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, StageResult

EnrichmentInputT_contra = TypeVar("EnrichmentInputT_contra", contravariant=True)
EnrichmentT_co = TypeVar("EnrichmentT_co", covariant=True)


@runtime_checkable
class EnrichmentProvider(Protocol[EnrichmentInputT_contra, EnrichmentT_co]):
    async def enrich(
        self, context: ImportPipelineContext, value: EnrichmentInputT_contra
    ) -> StageResult[EnrichmentT_co]: ...
