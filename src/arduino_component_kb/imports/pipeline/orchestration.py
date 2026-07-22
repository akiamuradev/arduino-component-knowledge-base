"""Unwired orchestration skeleton that verifies stage ordering and context continuity."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from arduino_component_kb.imports.pipeline.context import (
    PIPELINE_ORDER,
    ImportPipelineContext,
    PipelineStage,
)


class PipelineStep(Protocol):
    @property
    def stage(self) -> PipelineStage: ...

    async def run(self, context: ImportPipelineContext) -> ImportPipelineContext: ...


class PipelineOrchestrator:
    """Minimal sequencing contract; stage implementations and data flow arrive later."""

    def __init__(self, steps: Sequence[PipelineStep]) -> None:
        self.steps = tuple(steps)
        if tuple(step.stage for step in self.steps) != PIPELINE_ORDER:
            raise ValueError("pipeline_definition_order_invalid")

    async def run(self, context: ImportPipelineContext) -> ImportPipelineContext:
        current = context
        for step in self.steps:
            previous_count = len(current.executions)
            updated = await step.run(current)
            if (
                updated.run_id != current.run_id
                or updated.source_key != current.source_key
                or updated.source_locator != current.source_locator
                or len(updated.executions) != previous_count + 1
                or updated.executions[:-1] != current.executions
                or updated.executions[-1].stage is not step.stage
            ):
                raise ValueError("pipeline_step_context_invalid")
            current = updated
        return current
