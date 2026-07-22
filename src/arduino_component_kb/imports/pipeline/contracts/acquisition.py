"""Acquisition boundary."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, StageResult

RequestT_contra = TypeVar("RequestT_contra", contravariant=True)
ArtifactT_co = TypeVar("ArtifactT_co", covariant=True)


@runtime_checkable
class SourceAcquirer(Protocol[RequestT_contra, ArtifactT_co]):
    async def acquire(
        self, context: ImportPipelineContext, request: RequestT_contra
    ) -> StageResult[ArtifactT_co]: ...
