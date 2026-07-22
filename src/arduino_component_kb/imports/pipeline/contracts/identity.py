"""Component identity resolution boundary."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from arduino_component_kb.imports.pipeline.context import ImportPipelineContext, StageResult

NormalizedT_contra = TypeVar("NormalizedT_contra", contravariant=True)
IdentityT_co = TypeVar("IdentityT_co", covariant=True)


@runtime_checkable
class IdentityResolver(Protocol[NormalizedT_contra, IdentityT_co]):
    async def resolve(
        self, context: ImportPipelineContext, facts: NormalizedT_contra
    ) -> StageResult[IdentityT_co]: ...
