"""Persistence port owned by the import domain."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, StageResult

DraftT_contra = TypeVar("DraftT_contra", contravariant=True)
PersistedT_co = TypeVar("PersistedT_co", covariant=True)


@runtime_checkable
class ImportPersistenceGateway(Protocol[DraftT_contra, PersistedT_co]):
    async def persist(
        self, context: ImportPipelineContext, draft: DraftT_contra
    ) -> StageResult[PersistedT_co]: ...
