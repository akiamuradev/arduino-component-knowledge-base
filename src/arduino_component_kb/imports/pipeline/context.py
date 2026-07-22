"""Infrastructure-free context and stage result types for import orchestration."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_SOURCE_KEY = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,39}$")


class PipelineStage(StrEnum):
    ACQUISITION = "acquisition"
    EXTRACTION = "extraction"
    NORMALIZATION = "normalization"
    IDENTITY = "identity"
    ENRICHMENT = "enrichment"
    EVALUATION = "evaluation"
    COMPOSITION = "composition"
    PERSISTENCE = "persistence"


PIPELINE_ORDER: tuple[PipelineStage, ...] = tuple(PipelineStage)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name}_must_be_timezone_aware")


@dataclass(frozen=True, slots=True)
class StageExecution:
    stage: PipelineStage
    started_at: datetime
    completed_at: datetime
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(self.started_at, "stage_started_at")
        _require_aware(self.completed_at, "stage_completed_at")
        if self.completed_at < self.started_at:
            raise ValueError("stage_completed_before_start")
        if any(not value or len(value) > 160 for value in self.warnings):
            raise ValueError("stage_warning_invalid")
        if len(set(self.warnings)) != len(self.warnings):
            raise ValueError("stage_warnings_must_be_unique")

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> StageExecution:
        stage = value.get("stage")
        started_at = value.get("started_at")
        completed_at = value.get("completed_at")
        warnings = value.get("warnings", [])
        if (
            not isinstance(stage, str)
            or not isinstance(started_at, str)
            or not isinstance(completed_at, str)
            or not isinstance(warnings, list)
            or not all(isinstance(item, str) for item in warnings)
        ):
            raise ValueError("stage_execution_payload_invalid")
        return cls(
            stage=PipelineStage(stage),
            started_at=datetime.fromisoformat(started_at),
            completed_at=datetime.fromisoformat(completed_at),
            warnings=tuple(warnings),
        )


@dataclass(frozen=True, slots=True)
class ImportPipelineContext:
    run_id: UUID
    source_key: str
    source_locator: str
    pipeline_version: str
    started_at: datetime
    executions: tuple[StageExecution, ...] = ()

    def __post_init__(self) -> None:
        if _SOURCE_KEY.fullmatch(self.source_key) is None:
            raise ValueError("pipeline_source_key_invalid")
        if not self.source_locator.strip() or len(self.source_locator) > 1_000:
            raise ValueError("pipeline_source_locator_invalid")
        if _VERSION.fullmatch(self.pipeline_version) is None:
            raise ValueError("pipeline_version_invalid")
        _require_aware(self.started_at, "pipeline_started_at")
        stages = tuple(execution.stage for execution in self.executions)
        if stages != PIPELINE_ORDER[: len(stages)]:
            raise ValueError("pipeline_execution_order_invalid")
        if self.executions and self.executions[0].started_at < self.started_at:
            raise ValueError("pipeline_stage_precedes_run")
        for previous, current in zip(self.executions, self.executions[1:], strict=False):
            if current.started_at < previous.completed_at:
                raise ValueError("pipeline_stages_overlap")

    @property
    def next_stage(self) -> PipelineStage | None:
        if len(self.executions) == len(PIPELINE_ORDER):
            return None
        return PIPELINE_ORDER[len(self.executions)]

    def advance(self, execution: StageExecution) -> ImportPipelineContext:
        if execution.stage is not self.next_stage:
            raise ValueError("pipeline_stage_out_of_order")
        return replace(self, executions=(*self.executions, execution))

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "source_key": self.source_key,
            "source_locator": self.source_locator,
            "pipeline_version": self.pipeline_version,
            "started_at": self.started_at.isoformat(),
            "executions": [execution.as_dict() for execution in self.executions],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ImportPipelineContext:
        run_id = value.get("run_id")
        source_key = value.get("source_key")
        source_locator = value.get("source_locator")
        pipeline_version = value.get("pipeline_version")
        started_at = value.get("started_at")
        executions = value.get("executions", [])
        if (
            not isinstance(run_id, str)
            or not isinstance(source_key, str)
            or not isinstance(source_locator, str)
            or not isinstance(pipeline_version, str)
            or not isinstance(started_at, str)
            or not isinstance(executions, list)
            or not all(isinstance(item, dict) for item in executions)
        ):
            raise ValueError("pipeline_context_payload_invalid")
        return cls(
            run_id=UUID(run_id),
            source_key=source_key,
            source_locator=source_locator,
            pipeline_version=pipeline_version,
            started_at=datetime.fromisoformat(started_at),
            executions=tuple(StageExecution.from_dict(item) for item in executions),
        )

    @classmethod
    def from_json(cls, value: str) -> ImportPipelineContext:
        decoded: object = json.loads(value)
        if not isinstance(decoded, dict):
            raise ValueError("pipeline_context_payload_invalid")
        return cls.from_dict(decoded)


@dataclass(frozen=True, slots=True)
class StageResult[StageValueT]:
    stage: PipelineStage
    context: ImportPipelineContext
    value: StageValueT

    def __post_init__(self) -> None:
        if not self.context.executions or self.context.executions[-1].stage is not self.stage:
            raise ValueError("stage_result_context_mismatch")
