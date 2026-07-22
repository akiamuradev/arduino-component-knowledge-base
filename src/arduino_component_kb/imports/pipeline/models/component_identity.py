"""Evidence-backed component identity candidates produced before enrichment."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import ClassVar

from arduino_component_kb.imports.pipeline.models.extracted_facts import IdentifierKind
from arduino_component_kb.imports.pipeline.models.normalized_facts import (
    NormalizedFacts,
    NormalizedIdentifier,
)
from arduino_component_kb.imports.pipeline.models.provenance import (
    EvidenceFragment,
    SourceArtifactMetadata,
)

_KEY = re.compile(r"^[a-z][a-z0-9-]{0,79}$")
_RULE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(code)
    return value


def _required_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ValueError(f"{key}_must_be_string")
    return item


def _optional_string(value: Mapping[str, object], key: str) -> str | None:
    item = value.get(key)
    if item is not None and not isinstance(item, str):
        raise ValueError(f"{key}_must_be_string_or_null")
    return item


def _required_int(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(f"{key}_must_be_integer")
    return item


def _object_list(value: Mapping[str, object], key: str) -> list[object]:
    items = value.get(key, [])
    if not isinstance(items, list):
        raise ValueError(f"{key}_must_be_array")
    return list(items)


def _bounded(value: str, code: str, maximum: int = 2_000) -> str:
    if not value.strip() or "\x00" in value or len(value) > maximum:
        raise ValueError(code)
    return value


def _evidence(value: Mapping[str, object]) -> tuple[EvidenceFragment, ...]:
    result = tuple(
        EvidenceFragment.from_dict(_mapping(item, "identity_evidence_invalid"))
        for item in _object_list(value, "evidence")
    )
    if not result:
        raise ValueError("identity_evidence_missing")
    return result


class ComponentKind(StrEnum):
    MODULE = "module"
    DEVELOPMENT_BOARD = "development_board"
    DISCRETE_COMPONENT = "discrete_component"
    INTEGRATED_CIRCUIT = "integrated_circuit"
    CONNECTOR = "connector"
    GENERIC_UNKNOWN = "generic_unknown"


class IdentityConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IdentityResolutionStatus(StrEnum):
    AUTO_RESOLVED = "auto_resolved"
    REVIEW_REQUIRED = "review_required"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class IdentityValue:
    value: str
    rule_id: str
    evidence: tuple[EvidenceFragment, ...]

    def __post_init__(self) -> None:
        _bounded(self.value, "identity_value_invalid", 500)
        if _RULE_ID.fullmatch(self.rule_id) is None:
            raise ValueError("identity_value_rule_invalid")
        if not self.evidence:
            raise ValueError("identity_value_evidence_missing")

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "rule_id": self.rule_id,
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> IdentityValue:
        return cls(
            _required_string(value, "value"),
            _required_string(value, "rule_id"),
            _evidence(value),
        )


@dataclass(frozen=True, slots=True)
class IdentityAlias:
    value: str
    reason: str
    evidence: tuple[EvidenceFragment, ...]

    def __post_init__(self) -> None:
        _bounded(self.value, "identity_alias_invalid", 500)
        if _RULE_ID.fullmatch(self.reason) is None:
            raise ValueError("identity_alias_reason_invalid")
        if not self.evidence:
            raise ValueError("identity_alias_evidence_missing")

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "reason": self.reason,
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> IdentityAlias:
        return cls(
            _required_string(value, "value"),
            _required_string(value, "reason"),
            _evidence(value),
        )


@dataclass(frozen=True, slots=True)
class ScoreContribution:
    rule_id: str
    signal: str
    weight: int
    reason: str
    evidence: tuple[EvidenceFragment, ...]

    def __post_init__(self) -> None:
        if _RULE_ID.fullmatch(self.rule_id) is None:
            raise ValueError("score_rule_id_invalid")
        _bounded(self.signal, "score_signal_invalid", 1_000)
        _bounded(self.reason, "score_reason_invalid", 1_000)
        if self.weight == 0 or not -100 <= self.weight <= 100:
            raise ValueError("score_weight_invalid")
        if not self.evidence:
            raise ValueError("score_evidence_missing")

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "signal": self.signal,
            "weight": self.weight,
            "reason": self.reason,
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ScoreContribution:
        return cls(
            _required_string(value, "rule_id"),
            _required_string(value, "signal"),
            _required_int(value, "weight"),
            _required_string(value, "reason"),
            _evidence(value),
        )


@dataclass(frozen=True, slots=True)
class CategoryCandidate:
    category_key: str
    score: int
    breakdown: tuple[ScoreContribution, ...]

    def __post_init__(self) -> None:
        if _KEY.fullmatch(self.category_key) is None:
            raise ValueError("category_candidate_key_invalid")
        if not 0 <= self.score <= 100:
            raise ValueError("category_candidate_score_invalid")
        if not self.breakdown:
            raise ValueError("category_candidate_breakdown_missing")

    @property
    def evidence(self) -> tuple[EvidenceFragment, ...]:
        return tuple(
            dict.fromkeys(item for contribution in self.breakdown for item in contribution.evidence)
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "category_key": self.category_key,
            "score": self.score,
            "breakdown": [item.as_dict() for item in self.breakdown],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> CategoryCandidate:
        return cls(
            _required_string(value, "category_key"),
            _required_int(value, "score"),
            tuple(
                ScoreContribution.from_dict(_mapping(item, "score_contribution_invalid"))
                for item in _object_list(value, "breakdown")
            ),
        )


@dataclass(frozen=True, slots=True)
class KindCandidate:
    kind: ComponentKind
    score: int
    breakdown: tuple[ScoreContribution, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("kind_candidate_score_invalid")
        if not self.breakdown:
            raise ValueError("kind_candidate_breakdown_missing")

    @property
    def evidence(self) -> tuple[EvidenceFragment, ...]:
        return tuple(
            dict.fromkeys(item for contribution in self.breakdown for item in contribution.evidence)
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "score": self.score,
            "breakdown": [item.as_dict() for item in self.breakdown],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> KindCandidate:
        return cls(
            ComponentKind(_required_string(value, "kind")),
            _required_int(value, "score"),
            tuple(
                ScoreContribution.from_dict(_mapping(item, "score_contribution_invalid"))
                for item in _object_list(value, "breakdown")
            ),
        )


@dataclass(frozen=True, slots=True)
class ComponentIdentity:
    SCHEMA_VERSION: ClassVar[str] = "component-identity/v1"

    artifact: SourceArtifactMetadata
    normalized_facts_sha256: str
    normalized_facts: NormalizedFacts
    canonical_name: IdentityValue
    manufacturer: IdentityValue | None
    product_identifiers: tuple[NormalizedIdentifier, ...]
    part_numbers: tuple[NormalizedIdentifier, ...]
    primary_ic_candidates: tuple[NormalizedIdentifier, ...]
    aliases: tuple[IdentityAlias, ...]
    component_kind: ComponentKind
    kind_candidates: tuple[KindCandidate, ...]
    selected_category: str | None
    category_candidates: tuple[CategoryCandidate, ...]
    confidence: IdentityConfidence
    resolution_status: IdentityResolutionStatus
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", self.normalized_facts_sha256) is None:
            raise ValueError("identity_input_sha256_invalid")
        if self.normalized_facts.artifact != self.artifact:
            raise ValueError("identity_artifact_mismatch")
        actual_sha256 = sha256(self.normalized_facts.to_json().encode()).hexdigest()
        if actual_sha256 != self.normalized_facts_sha256:
            raise ValueError("identity_input_sha256_mismatch")
        if self.selected_category is not None and _KEY.fullmatch(self.selected_category) is None:
            raise ValueError("identity_selected_category_invalid")
        if not self.kind_candidates:
            raise ValueError("identity_kind_candidates_missing")
        if self.kind_candidates[0].kind is not self.component_kind:
            raise ValueError("identity_component_kind_candidate_mismatch")
        if len({item.kind for item in self.kind_candidates}) != len(self.kind_candidates):
            raise ValueError("identity_kind_candidates_duplicate")
        if tuple(self.kind_candidates) != tuple(
            sorted(self.kind_candidates, key=lambda item: (-item.score, item.kind.value))
        ):
            raise ValueError("identity_kind_candidates_order_invalid")
        if len({item.category_key for item in self.category_candidates}) != len(
            self.category_candidates
        ):
            raise ValueError("identity_category_candidates_duplicate")
        if tuple(self.category_candidates) != tuple(
            sorted(
                self.category_candidates,
                key=lambda item: (-item.score, item.category_key),
            )
        ):
            raise ValueError("identity_category_candidates_order_invalid")
        if self.selected_category is not None and (
            not self.category_candidates
            or self.category_candidates[0].category_key != self.selected_category
        ):
            raise ValueError("identity_category_candidate_mismatch")
        expected_confidence = {
            IdentityResolutionStatus.AUTO_RESOLVED: IdentityConfidence.HIGH,
            IdentityResolutionStatus.REVIEW_REQUIRED: IdentityConfidence.MEDIUM,
            IdentityResolutionStatus.UNRESOLVED: IdentityConfidence.LOW,
        }[self.resolution_status]
        if self.confidence is not expected_confidence:
            raise ValueError("identity_resolution_confidence_mismatch")
        if (self.resolution_status is IdentityResolutionStatus.AUTO_RESOLVED) != (
            self.selected_category is not None
        ):
            raise ValueError("identity_resolution_selection_mismatch")
        if any(item.kind is IdentifierKind.PART_NUMBER for item in self.product_identifiers):
            raise ValueError("identity_product_identifier_kind_invalid")
        if any(item.kind is not IdentifierKind.PART_NUMBER for item in self.part_numbers):
            raise ValueError("identity_part_number_kind_invalid")
        if any(item.kind is not IdentifierKind.PART_NUMBER for item in self.primary_ic_candidates):
            raise ValueError("identity_primary_ic_kind_invalid")
        if self.component_kind is ComponentKind.MODULE:
            primary_values = {
                item.trace.normalized_value.casefold() for item in self.primary_ic_candidates
            }
            if any(alias.value.casefold() in primary_values for alias in self.aliases):
                raise ValueError("identity_module_primary_ic_alias_forbidden")
            if self.selected_category == "integrated-circuits":
                raise ValueError("identity_module_ic_category_forbidden")
        evidence_groups = [
            self.canonical_name.evidence,
            *(alias.evidence for alias in self.aliases),
            *(candidate.evidence for candidate in self.kind_candidates),
            *(candidate.evidence for candidate in self.category_candidates),
            *(item.evidence for item in self.product_identifiers),
            *(item.evidence for item in self.part_numbers),
            *(item.evidence for item in self.primary_ic_candidates),
        ]
        if self.manufacturer is not None:
            evidence_groups.append(self.manufacturer.evidence)
        if any(item.source != self.artifact.source for group in evidence_groups for item in group):
            raise ValueError("identity_evidence_source_mismatch")
        if any(not value or len(value) > 160 for value in self.warnings):
            raise ValueError("identity_warning_invalid")
        if len(set(self.warnings)) != len(self.warnings):
            raise ValueError("identity_warnings_must_be_unique")

    @property
    def evidence(self) -> tuple[EvidenceFragment, ...]:
        groups = [
            self.canonical_name.evidence,
            *(alias.evidence for alias in self.aliases),
            *(candidate.evidence for candidate in self.kind_candidates),
            *(candidate.evidence for candidate in self.category_candidates),
            *(item.evidence for item in self.product_identifiers),
            *(item.evidence for item in self.part_numbers),
            *(item.evidence for item in self.primary_ic_candidates),
        ]
        if self.manufacturer is not None:
            groups.append(self.manufacturer.evidence)
        return tuple(dict.fromkeys(item for group in groups for item in group))

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "artifact": self.artifact.as_dict(),
            "normalized_facts_sha256": self.normalized_facts_sha256,
            "normalized_facts": self.normalized_facts.as_dict(),
            "canonical_name": self.canonical_name.as_dict(),
            "manufacturer": self.manufacturer.as_dict() if self.manufacturer else None,
            "product_identifiers": [item.as_dict() for item in self.product_identifiers],
            "part_numbers": [item.as_dict() for item in self.part_numbers],
            "primary_ic_candidates": [item.as_dict() for item in self.primary_ic_candidates],
            "aliases": [item.as_dict() for item in self.aliases],
            "component_kind": self.component_kind.value,
            "kind_candidates": [item.as_dict() for item in self.kind_candidates],
            "selected_category": self.selected_category,
            "category_candidates": [item.as_dict() for item in self.category_candidates],
            "confidence": self.confidence.value,
            "resolution_status": self.resolution_status.value,
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ComponentIdentity:
        if value.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("component_identity_schema_version_unsupported")
        manufacturer = value.get("manufacturer")
        selected_category = _optional_string(value, "selected_category")
        return cls(
            artifact=SourceArtifactMetadata.from_dict(
                _mapping(value.get("artifact"), "component_identity_artifact_invalid")
            ),
            normalized_facts_sha256=_required_string(value, "normalized_facts_sha256"),
            normalized_facts=NormalizedFacts.from_dict(
                _mapping(value.get("normalized_facts"), "component_identity_input_invalid")
            ),
            canonical_name=IdentityValue.from_dict(
                _mapping(value.get("canonical_name"), "canonical_name_invalid")
            ),
            manufacturer=(
                IdentityValue.from_dict(_mapping(manufacturer, "identity_manufacturer_invalid"))
                if manufacturer is not None
                else None
            ),
            product_identifiers=tuple(
                NormalizedIdentifier.from_dict(_mapping(item, "product_identifier_invalid"))
                for item in _object_list(value, "product_identifiers")
            ),
            part_numbers=tuple(
                NormalizedIdentifier.from_dict(_mapping(item, "part_number_invalid"))
                for item in _object_list(value, "part_numbers")
            ),
            primary_ic_candidates=tuple(
                NormalizedIdentifier.from_dict(_mapping(item, "primary_ic_candidate_invalid"))
                for item in _object_list(value, "primary_ic_candidates")
            ),
            aliases=tuple(
                IdentityAlias.from_dict(_mapping(item, "identity_alias_invalid"))
                for item in _object_list(value, "aliases")
            ),
            component_kind=ComponentKind(_required_string(value, "component_kind")),
            kind_candidates=tuple(
                KindCandidate.from_dict(_mapping(item, "kind_candidate_invalid"))
                for item in _object_list(value, "kind_candidates")
            ),
            selected_category=selected_category,
            category_candidates=tuple(
                CategoryCandidate.from_dict(_mapping(item, "category_candidate_invalid"))
                for item in _object_list(value, "category_candidates")
            ),
            confidence=IdentityConfidence(_required_string(value, "confidence")),
            resolution_status=IdentityResolutionStatus(
                _required_string(value, "resolution_status")
            ),
            warnings=tuple(
                _required_string({"warning": item}, "warning")
                for item in _object_list(value, "warnings")
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> ComponentIdentity:
        decoded: object = json.loads(value)
        return cls.from_dict(_mapping(decoded, "component_identity_payload_invalid"))
