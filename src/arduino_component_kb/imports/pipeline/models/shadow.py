"""Privacy-safe old/new import comparison report."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from arduino_component_kb.imports.pipeline.models.runtime import PipelineRunOutcome


@dataclass(frozen=True, slots=True)
class ShadowFieldConflict:
    field: str
    legacy_sha256: str
    pipeline_sha256: str

    def as_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "legacy_sha256": self.legacy_sha256,
            "pipeline_sha256": self.pipeline_sha256,
        }


@dataclass(frozen=True, slots=True)
class ShadowComparisonReport:
    run_id: UUID
    source_key: str
    source_file_path: str
    legacy_status: str
    pipeline_status: str
    legacy_field_count: int
    pipeline_field_count: int
    common_field_count: int
    missing_pipeline_fields: tuple[str, ...]
    additional_pipeline_fields: tuple[str, ...]
    conflicts: tuple[ShadowFieldConflict, ...]
    quality_route: str | None
    quality_score_basis_points: int | None
    parser_warnings: tuple[str, ...]
    kicad_candidate_count: int
    kicad_auto_accepted_count: int
    kicad_review_count: int
    kicad_rejected_count: int
    kicad_candidate_precision_basis_points: int | None
    kicad_precision_status: str
    execution_time_ms: float
    failure: dict[str, object] | None = None

    @property
    def field_coverage_basis_points(self) -> int:
        if self.legacy_field_count == 0:
            return 1_000
        return min(1_000, self.common_field_count * 1_000 // self.legacy_field_count)

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": str(self.run_id),
            "source_key": self.source_key,
            "source_file_path": self.source_file_path,
            "legacy_status": self.legacy_status,
            "pipeline_status": self.pipeline_status,
            "field_coverage": {
                "legacy_count": self.legacy_field_count,
                "pipeline_count": self.pipeline_field_count,
                "common_count": self.common_field_count,
                "basis_points": self.field_coverage_basis_points,
                "missing_pipeline_fields": list(self.missing_pipeline_fields),
                "additional_pipeline_fields": list(self.additional_pipeline_fields),
            },
            "conflicts": [item.as_dict() for item in self.conflicts],
            "quality": {
                "route": self.quality_route,
                "score_basis_points": self.quality_score_basis_points,
            },
            "parser_warnings": list(self.parser_warnings),
            "kicad": {
                "candidate_count": self.kicad_candidate_count,
                "auto_accepted_count": self.kicad_auto_accepted_count,
                "review_count": self.kicad_review_count,
                "rejected_count": self.kicad_rejected_count,
                "precision_basis_points": self.kicad_candidate_precision_basis_points,
                "precision_status": self.kicad_precision_status,
            },
            "execution_time_ms": self.execution_time_ms,
            "failure": self.failure,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def shadow_value_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ShadowRunResult:
    outcome: PipelineRunOutcome
    comparison: ShadowComparisonReport
