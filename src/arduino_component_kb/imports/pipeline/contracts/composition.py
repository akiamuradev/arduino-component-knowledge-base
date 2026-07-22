"""Review draft composition boundary."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, StageResult

CompositionInputT_contra = TypeVar("CompositionInputT_contra", contravariant=True)
DraftT_co = TypeVar("DraftT_co", covariant=True)


@runtime_checkable
class CardComposer(Protocol[CompositionInputT_contra, DraftT_co]):
    async def compose(
        self, context: ImportPipelineContext, value: CompositionInputT_contra
    ) -> StageResult[DraftT_co]: ...
