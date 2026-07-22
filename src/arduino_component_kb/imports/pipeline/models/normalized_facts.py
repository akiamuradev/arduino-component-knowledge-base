"""Deterministic semantic facts produced after evidence-preserving extraction."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import ClassVar

from arduino_component_kb.imports.pipeline.models.extracted_facts import (
    ExtractedFacts,
    ExtractedField,
    IdentifierKind,
    UnknownFact,
)
from arduino_component_kb.imports.pipeline.models.provenance import (
    EvidenceFragment,
    SourceArtifactMetadata,
)

_RULE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,39}$")
_TAXONOMY_PATH = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")


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


def _object_list(value: Mapping[str, object], key: str) -> list[object]:
    items = value.get(key, [])
    if not isinstance(items, list):
        raise ValueError(f"{key}_must_be_array")
    return list(items)


def _bounded(value: str, code: str, maximum: int = 10_000) -> str:
    if not value.strip() or "\x00" in value or len(value) > maximum:
        raise ValueError(code)
    return value


def _evidence(value: Mapping[str, object]) -> tuple[EvidenceFragment, ...]:
    result = tuple(
        EvidenceFragment.from_dict(_mapping(item, "normalization_evidence_invalid"))
        for item in _object_list(value, "evidence")
    )
    if not result:
        raise ValueError("normalization_evidence_missing")
    return result


class NormalizationConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NormalizationProfile(StrEnum):
    SENSOR = "sensor"
    DISPLAY = "display"
    ACTUATOR = "actuator"
    BOARD = "board"
    COMMUNICATION = "communication"
    GENERIC = "generic"


@dataclass(frozen=True, slots=True)
class NormalizationTrace:
    original_value: str
    raw_value: str
    normalized_value: str
    rule_id: str
    rule_version: str
    confidence: NormalizationConfidence

    def __post_init__(self) -> None:
        _bounded(self.original_value, "normalization_original_value_invalid")
        _bounded(self.raw_value, "normalization_raw_value_invalid", 100_000)
        _bounded(self.normalized_value, "normalization_value_invalid")
        if _RULE_ID.fullmatch(self.rule_id) is None:
            raise ValueError("normalization_rule_id_invalid")
        if _VERSION.fullmatch(self.rule_version) is None:
            raise ValueError("normalization_rule_version_invalid")

    def as_dict(self) -> dict[str, str]:
        return {
            "original_value": self.original_value,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "confidence": self.confidence.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> NormalizationTrace:
        return cls(
            original_value=_required_string(value, "original_value"),
            raw_value=_required_string(value, "raw_value"),
            normalized_value=_required_string(value, "normalized_value"),
            rule_id=_required_string(value, "rule_id"),
            rule_version=_required_string(value, "rule_version"),
            confidence=NormalizationConfidence(_required_string(value, "confidence")),
        )


@dataclass(frozen=True, slots=True)
class NormalizedSpecification:
    taxonomy_path: str
    canonical_label: str
    original_label: str
    normalized_unit: str | None
    trace: NormalizationTrace
    evidence: tuple[EvidenceFragment, ...]

    def __post_init__(self) -> None:
        if _TAXONOMY_PATH.fullmatch(self.taxonomy_path) is None:
            raise ValueError("normalized_specification_taxonomy_invalid")
        _bounded(self.canonical_label, "normalized_specification_label_invalid", 500)
        _bounded(self.original_label, "normalized_specification_original_label_invalid", 500)
        if self.normalized_unit is not None:
            _bounded(self.normalized_unit, "normalized_specification_unit_invalid", 40)
        if not self.evidence:
            raise ValueError("normalized_specification_evidence_missing")

    def as_dict(self) -> dict[str, object]:
        return {
            "taxonomy_path": self.taxonomy_path,
            "canonical_label": self.canonical_label,
            "original_label": self.original_label,
            "normalized_unit": self.normalized_unit,
            "trace": self.trace.as_dict(),
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> NormalizedSpecification:
        return cls(
            taxonomy_path=_required_string(value, "taxonomy_path"),
            canonical_label=_required_string(value, "canonical_label"),
            original_label=_required_string(value, "original_label"),
            normalized_unit=_optional_string(value, "normalized_unit"),
            trace=NormalizationTrace.from_dict(
                _mapping(value.get("trace"), "normalization_trace_invalid")
            ),
            evidence=_evidence(value),
        )


@dataclass(frozen=True, slots=True)
class NormalizedTextFact:
    semantic_path: str
    trace: NormalizationTrace
    evidence: tuple[EvidenceFragment, ...]

    def __post_init__(self) -> None:
        if _TAXONOMY_PATH.fullmatch(self.semantic_path) is None:
            raise ValueError("normalized_text_semantic_path_invalid")
        if not self.evidence:
            raise ValueError("normalized_text_evidence_missing")

    def as_dict(self) -> dict[str, object]:
        return {
            "semantic_path": self.semantic_path,
            "trace": self.trace.as_dict(),
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> NormalizedTextFact:
        return cls(
            semantic_path=_required_string(value, "semantic_path"),
            trace=NormalizationTrace.from_dict(
                _mapping(value.get("trace"), "normalization_trace_invalid")
            ),
            evidence=_evidence(value),
        )


@dataclass(frozen=True, slots=True)
class NormalizedIdentifier:
    kind: IdentifierKind
    trace: NormalizationTrace
    evidence: tuple[EvidenceFragment, ...]

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError("normalized_identifier_evidence_missing")

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "trace": self.trace.as_dict(),
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> NormalizedIdentifier:
        return cls(
            kind=IdentifierKind(_required_string(value, "kind")),
            trace=NormalizationTrace.from_dict(
                _mapping(value.get("trace"), "normalization_trace_invalid")
            ),
            evidence=_evidence(value),
        )


@dataclass(frozen=True, slots=True)
class UnmappedSpecification:
    original_label: str
    original_value: str
    raw_value: str
    reason: str
    evidence: tuple[EvidenceFragment, ...]

    def __post_init__(self) -> None:
        _bounded(self.original_label, "unmapped_specification_label_invalid", 500)
        _bounded(self.original_value, "unmapped_specification_value_invalid")
        _bounded(self.raw_value, "unmapped_specification_raw_invalid", 100_000)
        if _RULE_ID.fullmatch(self.reason) is None:
            raise ValueError("unmapped_specification_reason_invalid")
        if not self.evidence:
            raise ValueError("unmapped_specification_evidence_missing")

    def as_dict(self) -> dict[str, object]:
        return {
            "original_label": self.original_label,
            "original_value": self.original_value,
            "raw_value": self.raw_value,
            "reason": self.reason,
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> UnmappedSpecification:
        return cls(
            original_label=_required_string(value, "original_label"),
            original_value=_required_string(value, "original_value"),
            raw_value=_required_string(value, "raw_value"),
            reason=_required_string(value, "reason"),
            evidence=_evidence(value),
        )


@dataclass(frozen=True, slots=True)
class NormalizationConflict:
    taxonomy_path: str
    normalized_values: tuple[str, ...]
    evidence: tuple[EvidenceFragment, ...]
    code: str = "incompatible_values"

    def __post_init__(self) -> None:
        if _TAXONOMY_PATH.fullmatch(self.taxonomy_path) is None:
            raise ValueError("normalization_conflict_taxonomy_invalid")
        if len(self.normalized_values) < 2 or len(set(self.normalized_values)) < 2:
            raise ValueError("normalization_conflict_values_invalid")
        if _RULE_ID.fullmatch(self.code) is None:
            raise ValueError("normalization_conflict_code_invalid")
        if not self.evidence:
            raise ValueError("normalization_conflict_evidence_missing")

    def as_dict(self) -> dict[str, object]:
        return {
            "taxonomy_path": self.taxonomy_path,
            "normalized_values": list(self.normalized_values),
            "code": self.code,
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> NormalizationConflict:
        normalized_values = value.get("normalized_values")
        if not isinstance(normalized_values, list) or not all(
            isinstance(item, str) for item in normalized_values
        ):
            raise ValueError("normalization_conflict_values_invalid")
        return cls(
            taxonomy_path=_required_string(value, "taxonomy_path"),
            normalized_values=tuple(normalized_values),
            code=_required_string(value, "code"),
            evidence=_evidence(value),
        )


@dataclass(frozen=True, slots=True)
class NormalizedFacts:
    SCHEMA_VERSION: ClassVar[str] = "normalized-facts/v1"

    artifact: SourceArtifactMetadata
    extracted_facts_sha256: str
    extracted_facts: ExtractedFacts
    profile: NormalizationProfile
    specifications: tuple[NormalizedSpecification, ...] = ()
    unmapped_specifications: tuple[UnmappedSpecification, ...] = ()
    interfaces: tuple[NormalizedTextFact, ...] = ()
    unmapped_interfaces: tuple[NormalizedTextFact, ...] = ()
    manufacturers: tuple[NormalizedTextFact, ...] = ()
    identifiers: tuple[NormalizedIdentifier, ...] = ()
    primary_ics: tuple[NormalizedIdentifier, ...] = ()
    conflicts: tuple[NormalizationConflict, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", self.extracted_facts_sha256) is None:
            raise ValueError("normalized_facts_input_sha256_invalid")
        if self.extracted_facts.artifact != self.artifact:
            raise ValueError("normalized_facts_artifact_mismatch")
        actual_sha256 = sha256(self.extracted_facts.to_json().encode()).hexdigest()
        if actual_sha256 != self.extracted_facts_sha256:
            raise ValueError("normalized_facts_input_sha256_mismatch")
        evidence_groups = (
            self.specifications,
            self.unmapped_specifications,
            self.interfaces,
            self.unmapped_interfaces,
            self.manufacturers,
            self.identifiers,
            self.primary_ics,
            self.conflicts,
        )
        if any(
            item.source != self.artifact.source
            for group in evidence_groups
            for fact in group
            for item in fact.evidence
        ):
            raise ValueError("normalized_fact_source_mismatch")
        if any(not warning or len(warning) > 160 for warning in self.warnings):
            raise ValueError("normalization_warning_invalid")
        if len(set(self.warnings)) != len(self.warnings):
            raise ValueError("normalization_warnings_must_be_unique")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "artifact": self.artifact.as_dict(),
            "extracted_facts_sha256": self.extracted_facts_sha256,
            "extracted_facts": self.extracted_facts.as_dict(),
            "profile": self.profile.value,
            "specifications": [item.as_dict() for item in self.specifications],
            "unmapped_specifications": [item.as_dict() for item in self.unmapped_specifications],
            "interfaces": [item.as_dict() for item in self.interfaces],
            "unmapped_interfaces": [item.as_dict() for item in self.unmapped_interfaces],
            "manufacturers": [item.as_dict() for item in self.manufacturers],
            "identifiers": [item.as_dict() for item in self.identifiers],
            "primary_ics": [item.as_dict() for item in self.primary_ics],
            "conflicts": [item.as_dict() for item in self.conflicts],
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> NormalizedFacts:
        if value.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("normalized_facts_schema_version_unsupported")
        return cls(
            artifact=SourceArtifactMetadata.from_dict(
                _mapping(value.get("artifact"), "normalized_facts_artifact_invalid")
            ),
            extracted_facts_sha256=_required_string(value, "extracted_facts_sha256"),
            extracted_facts=ExtractedFacts.from_dict(
                _mapping(value.get("extracted_facts"), "normalized_facts_input_invalid")
            ),
            profile=NormalizationProfile(_required_string(value, "profile")),
            specifications=tuple(
                NormalizedSpecification.from_dict(
                    _mapping(item, "normalized_specification_invalid")
                )
                for item in _object_list(value, "specifications")
            ),
            unmapped_specifications=tuple(
                UnmappedSpecification.from_dict(_mapping(item, "unmapped_specification_invalid"))
                for item in _object_list(value, "unmapped_specifications")
            ),
            interfaces=tuple(
                NormalizedTextFact.from_dict(_mapping(item, "normalized_interface_invalid"))
                for item in _object_list(value, "interfaces")
            ),
            unmapped_interfaces=tuple(
                NormalizedTextFact.from_dict(_mapping(item, "unmapped_interface_invalid"))
                for item in _object_list(value, "unmapped_interfaces")
            ),
            manufacturers=tuple(
                NormalizedTextFact.from_dict(_mapping(item, "normalized_manufacturer_invalid"))
                for item in _object_list(value, "manufacturers")
            ),
            identifiers=tuple(
                NormalizedIdentifier.from_dict(_mapping(item, "normalized_identifier_invalid"))
                for item in _object_list(value, "identifiers")
            ),
            primary_ics=tuple(
                NormalizedIdentifier.from_dict(_mapping(item, "normalized_primary_ic_invalid"))
                for item in _object_list(value, "primary_ics")
            ),
            conflicts=tuple(
                NormalizationConflict.from_dict(_mapping(item, "normalization_conflict_invalid"))
                for item in _object_list(value, "conflicts")
            ),
            warnings=tuple(
                _required_string({"warning": item}, "warning")
                for item in _object_list(value, "warnings")
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> NormalizedFacts:
        decoded: object = json.loads(value)
        return cls.from_dict(_mapping(decoded, "normalized_facts_payload_invalid"))

    @property
    def source_unmapped_facts(self) -> tuple[ExtractedField[UnknownFact], ...]:
        return self.extracted_facts.unmapped_facts
