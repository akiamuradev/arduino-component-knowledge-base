"""Immutable pre-composition quality report and routing models."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import ClassVar

from arduino_component_kb.imports.pipeline.models.component_identity import ComponentIdentity
from arduino_component_kb.imports.pipeline.models.enrichment import EnrichmentCandidate
from arduino_component_kb.imports.pipeline.models.normalized_facts import (
    NormalizationProfile,
    NormalizedFacts,
)
from arduino_component_kb.imports.pipeline.models.provenance import EvidenceFragment

_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,119}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,39}$")


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(code)
    return value


def _required_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ValueError(f"{key}_must_be_string")
    return item


def _required_int(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(f"{key}_must_be_integer")
    return item


def _required_bool(value: Mapping[str, object], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ValueError(f"{key}_must_be_boolean")
    return item


def _object_list(value: Mapping[str, object], key: str) -> list[object]:
    items = value.get(key, [])
    if not isinstance(items, list):
        raise ValueError(f"{key}_must_be_array")
    return list(items)


def _string_list(value: Mapping[str, object], key: str) -> tuple[str, ...]:
    items = value.get(key, [])
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise ValueError(f"{key}_must_be_string_array")
    return tuple(items)


def _bounded(value: str, code: str, maximum: int = 2_000) -> None:
    if not value.strip() or "\x00" in value or len(value) > maximum:
        raise ValueError(code)


class QualityDimension(StrEnum):
    IDENTITY_CONFIDENCE = "identity_confidence"
    DESCRIPTION_COMPLETENESS = "description_completeness"
    SPECIFICATION_COVERAGE = "specification_coverage"
    MODULE_PINOUT_PRESENCE = "module_pinout_presence"
    SOURCE_PROVENANCE_COMPLETENESS = "source_provenance_completeness"
    CONFLICTS = "conflicts"
    ENRICHMENT_CONFIDENCE = "enrichment_confidence"
    EDUCATIONAL_USEFULNESS = "educational_usefulness"
    PUBLICATION_READINESS = "publication_readiness"


class QualityIssueSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class QualityIssueCause(StrEnum):
    SOURCE_MISSING = "source_missing"
    EXTRACTION_MISSING = "extraction_missing"
    CONFLICT = "conflict"
    POLICY = "policy"


class QualityRoute(StrEnum):
    REJECT = "reject"
    MANUAL_REVIEW = "manual_review"
    READY_TO_COMPOSE = "ready_to_compose"


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    severity: QualityIssueSeverity
    cause: QualityIssueCause
    dimension: QualityDimension
    message: str
    evidence: tuple[EvidenceFragment, ...] = ()

    def __post_init__(self) -> None:
        if _CODE.fullmatch(self.code) is None:
            raise ValueError("quality_issue_code_invalid")
        _bounded(self.message, "quality_issue_message_invalid", 1_000)
        if len(set(self.evidence)) != len(self.evidence):
            raise ValueError("quality_issue_evidence_duplicate")

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "cause": self.cause.value,
            "dimension": self.dimension.value,
            "message": self.message,
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> QualityIssue:
        return cls(
            code=_required_string(value, "code"),
            severity=QualityIssueSeverity(_required_string(value, "severity")),
            cause=QualityIssueCause(_required_string(value, "cause")),
            dimension=QualityDimension(_required_string(value, "dimension")),
            message=_required_string(value, "message"),
            evidence=tuple(
                EvidenceFragment.from_dict(_mapping(item, "quality_issue_evidence_invalid"))
                for item in _object_list(value, "evidence")
            ),
        )


@dataclass(frozen=True, slots=True)
class QualityDimensionScore:
    dimension: QualityDimension
    score_basis_points: int
    weight_basis_points: int
    applicable: bool
    explanation: str
    issue_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.score_basis_points <= 1_000:
            raise ValueError("quality_dimension_score_invalid")
        if not 1 <= self.weight_basis_points <= 1_000:
            raise ValueError("quality_dimension_weight_invalid")
        if not self.applicable and self.score_basis_points != 1_000:
            raise ValueError("quality_dimension_not_applicable_score_invalid")
        _bounded(self.explanation, "quality_dimension_explanation_invalid", 1_000)
        if any(_CODE.fullmatch(item) is None for item in self.issue_codes):
            raise ValueError("quality_dimension_issue_code_invalid")
        if len(set(self.issue_codes)) != len(self.issue_codes):
            raise ValueError("quality_dimension_issue_codes_duplicate")

    def as_dict(self) -> dict[str, object]:
        return {
            "dimension": self.dimension.value,
            "score_basis_points": self.score_basis_points,
            "score": self.score_basis_points / 1_000,
            "weight_basis_points": self.weight_basis_points,
            "applicable": self.applicable,
            "explanation": self.explanation,
            "issue_codes": list(self.issue_codes),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> QualityDimensionScore:
        score = value.get("score")
        if not isinstance(score, int | float) or isinstance(score, bool):
            raise ValueError("quality_dimension_decimal_score_invalid")
        result = cls(
            dimension=QualityDimension(_required_string(value, "dimension")),
            score_basis_points=_required_int(value, "score_basis_points"),
            weight_basis_points=_required_int(value, "weight_basis_points"),
            applicable=_required_bool(value, "applicable"),
            explanation=_required_string(value, "explanation"),
            issue_codes=_string_list(value, "issue_codes"),
        )
        if abs(result.score_basis_points / 1_000 - float(score)) > 0.000_001:
            raise ValueError("quality_dimension_decimal_score_mismatch")
        return result


@dataclass(frozen=True, slots=True)
class QualityEvaluationInput:
    facts: NormalizedFacts
    identity: ComponentIdentity
    enrichments: tuple[EnrichmentCandidate, ...] = ()

    def __post_init__(self) -> None:
        if self.identity.normalized_facts != self.facts:
            raise ValueError("quality_input_facts_mismatch")
        identity_sha256 = sha256(self.identity.to_json().encode()).hexdigest()
        if any(item.relation.identity_sha256 != identity_sha256 for item in self.enrichments):
            raise ValueError("quality_input_enrichment_identity_mismatch")
        keys = [
            (item.relation.symbol.record_id, item.relation.relation_type)
            for item in self.enrichments
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("quality_input_enrichment_duplicate")

    @property
    def input_sha256(self) -> str:
        payload = {
            "facts_sha256": sha256(self.facts.to_json().encode()).hexdigest(),
            "identity_sha256": sha256(self.identity.to_json().encode()).hexdigest(),
            "enrichments": [
                sha256(item.to_json().encode()).hexdigest() for item in self.enrichments
            ],
        }
        return sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class QualityReport:
    SCHEMA_VERSION: ClassVar[str] = "quality-report/v1"

    input_sha256: str
    profile: NormalizationProfile
    dimensions: tuple[QualityDimensionScore, ...]
    overall_score_basis_points: int
    route: QualityRoute
    issues: tuple[QualityIssue, ...]
    reject_threshold_basis_points: int
    ready_threshold_basis_points: int
    evaluator_version: str

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.input_sha256) is None:
            raise ValueError("quality_report_input_sha256_invalid")
        if tuple(item.dimension for item in self.dimensions) != tuple(QualityDimension):
            raise ValueError("quality_report_dimensions_invalid")
        if sum(item.weight_basis_points for item in self.dimensions) != 1_000:
            raise ValueError("quality_report_dimension_weights_invalid")
        expected_score = (
            sum(item.score_basis_points * item.weight_basis_points for item in self.dimensions)
            // 1_000
        )
        if self.overall_score_basis_points != expected_score:
            raise ValueError("quality_report_overall_score_mismatch")
        if not 0 <= self.reject_threshold_basis_points < self.ready_threshold_basis_points <= 1_000:
            raise ValueError("quality_report_thresholds_invalid")
        issue_codes = [item.code for item in self.issues]
        if len(issue_codes) != len(set(issue_codes)):
            raise ValueError("quality_report_issue_codes_duplicate")
        severity_order = {
            QualityIssueSeverity.BLOCKING: 0,
            QualityIssueSeverity.WARNING: 1,
            QualityIssueSeverity.SUGGESTION: 2,
        }
        if self.issues != tuple(
            sorted(
                self.issues,
                key=lambda item: (
                    severity_order[item.severity],
                    item.dimension.value,
                    item.code,
                ),
            )
        ):
            raise ValueError("quality_report_issues_order_invalid")
        known_codes = set(issue_codes)
        if any(
            code not in known_codes
            for dimension in self.dimensions
            for code in dimension.issue_codes
        ):
            raise ValueError("quality_report_dimension_issue_missing")
        blocking = any(item.severity is QualityIssueSeverity.BLOCKING for item in self.issues)
        warning = any(item.severity is QualityIssueSeverity.WARNING for item in self.issues)
        expected_route = (
            QualityRoute.REJECT
            if blocking or self.overall_score_basis_points < self.reject_threshold_basis_points
            else (
                QualityRoute.MANUAL_REVIEW
                if warning or self.overall_score_basis_points < self.ready_threshold_basis_points
                else QualityRoute.READY_TO_COMPOSE
            )
        )
        if self.route is not expected_route:
            raise ValueError("quality_report_route_mismatch")
        if _VERSION.fullmatch(self.evaluator_version) is None:
            raise ValueError("quality_report_evaluator_version_invalid")

    @property
    def overall_score(self) -> float:
        return self.overall_score_basis_points / 1_000

    @property
    def blocking_issues(self) -> tuple[QualityIssue, ...]:
        return tuple(item for item in self.issues if item.severity is QualityIssueSeverity.BLOCKING)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "input_sha256": self.input_sha256,
            "profile": self.profile.value,
            "dimensions": [item.as_dict() for item in self.dimensions],
            "overall_score_basis_points": self.overall_score_basis_points,
            "overall_score": self.overall_score,
            "route": self.route.value,
            "issues": [item.as_dict() for item in self.issues],
            "reject_threshold_basis_points": self.reject_threshold_basis_points,
            "ready_threshold_basis_points": self.ready_threshold_basis_points,
            "evaluator_version": self.evaluator_version,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> QualityReport:
        if value.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("quality_report_schema_version_unsupported")
        overall_score = value.get("overall_score")
        if not isinstance(overall_score, int | float) or isinstance(overall_score, bool):
            raise ValueError("quality_report_decimal_score_invalid")
        result = cls(
            input_sha256=_required_string(value, "input_sha256"),
            profile=NormalizationProfile(_required_string(value, "profile")),
            dimensions=tuple(
                QualityDimensionScore.from_dict(_mapping(item, "quality_dimension_invalid"))
                for item in _object_list(value, "dimensions")
            ),
            overall_score_basis_points=_required_int(value, "overall_score_basis_points"),
            route=QualityRoute(_required_string(value, "route")),
            issues=tuple(
                QualityIssue.from_dict(_mapping(item, "quality_issue_invalid"))
                for item in _object_list(value, "issues")
            ),
            reject_threshold_basis_points=_required_int(value, "reject_threshold_basis_points"),
            ready_threshold_basis_points=_required_int(value, "ready_threshold_basis_points"),
            evaluator_version=_required_string(value, "evaluator_version"),
        )
        if abs(result.overall_score - float(overall_score)) > 0.000_001:
            raise ValueError("quality_report_decimal_score_mismatch")
        return result

    @classmethod
    def from_json(cls, value: str) -> QualityReport:
        decoded: object = json.loads(value)
        return cls.from_dict(_mapping(decoded, "quality_report_payload_invalid"))
