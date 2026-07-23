"""Immutable review-draft models produced only by card composition."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import ClassVar

from arduino_component_kb.imports.pipeline.models.component_identity import ComponentIdentity
from arduino_component_kb.imports.pipeline.models.enrichment import (
    ComponentSymbolRelationType,
    EnrichmentCandidate,
)
from arduino_component_kb.imports.pipeline.models.extracted_facts import ResourceKind
from arduino_component_kb.imports.pipeline.models.kicad import KicadPin
from arduino_component_kb.imports.pipeline.models.normalized_facts import NormalizedFacts
from arduino_component_kb.imports.pipeline.models.provenance import (
    EvidenceFragment,
    SourceArtifactMetadata,
)
from arduino_component_kb.imports.pipeline.models.quality import (
    QualityEvaluationInput,
    QualityIssue,
    QualityIssueSeverity,
    QualityReport,
    QualityRoute,
)

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


def _evidence(value: Mapping[str, object], key: str) -> tuple[EvidenceFragment, ...]:
    return tuple(
        EvidenceFragment.from_dict(_mapping(item, f"{key}_evidence_invalid"))
        for item in _object_list(value, key)
    )


def _bounded(value: str, code: str, maximum: int = 10_000) -> None:
    if not value.strip() or "\x00" in value or len(value) > maximum:
        raise ValueError(code)


def _unique_evidence(value: tuple[EvidenceFragment, ...], code: str) -> None:
    if not value or len(set(value)) != len(value):
        raise ValueError(code)


class DraftConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DraftEnrichmentStatus(StrEnum):
    ACCEPTED = "accepted"
    PROPOSED = "proposed"


@dataclass(frozen=True, slots=True)
class DraftReviewMetadata:
    confidence: DraftConfidence
    review_required: bool
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.review_required != bool(self.reason_codes):
            raise ValueError("draft_review_reason_state_invalid")
        if any(_CODE.fullmatch(item) is None for item in self.reason_codes):
            raise ValueError("draft_review_reason_code_invalid")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("draft_review_reason_duplicate")

    def as_dict(self) -> dict[str, object]:
        return {
            "confidence": self.confidence.value,
            "review_required": self.review_required,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DraftReviewMetadata:
        return cls(
            DraftConfidence(_required_string(value, "confidence")),
            _required_bool(value, "review_required"),
            _string_list(value, "reason_codes"),
        )


@dataclass(frozen=True, slots=True)
class DraftText:
    value: str
    evidence: tuple[EvidenceFragment, ...]
    review: DraftReviewMetadata

    def __post_init__(self) -> None:
        _bounded(self.value, "draft_text_invalid", 100_000)
        _unique_evidence(self.evidence, "draft_text_evidence_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "evidence": [item.as_dict() for item in self.evidence],
            "review": self.review.as_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DraftText:
        return cls(
            _required_string(value, "value"),
            _evidence(value, "evidence"),
            DraftReviewMetadata.from_dict(_mapping(value.get("review"), "draft_review_invalid")),
        )


@dataclass(frozen=True, slots=True)
class DraftDescriptionSection:
    heading: str | None
    body: str
    evidence: tuple[EvidenceFragment, ...]
    review: DraftReviewMetadata

    def __post_init__(self) -> None:
        if self.heading is not None:
            _bounded(self.heading, "draft_description_heading_invalid", 500)
        _bounded(self.body, "draft_description_body_invalid", 100_000)
        _unique_evidence(self.evidence, "draft_description_evidence_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "heading": self.heading,
            "body": self.body,
            "evidence": [item.as_dict() for item in self.evidence],
            "review": self.review.as_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DraftDescriptionSection:
        return cls(
            _optional_string(value, "heading"),
            _required_string(value, "body"),
            _evidence(value, "evidence"),
            DraftReviewMetadata.from_dict(_mapping(value.get("review"), "draft_review_invalid")),
        )


@dataclass(frozen=True, slots=True)
class DraftSpecification:
    taxonomy_path: str | None
    label: str
    value: str
    raw_value: str
    unit: str | None
    evidence: tuple[EvidenceFragment, ...]
    review: DraftReviewMetadata

    def __post_init__(self) -> None:
        if self.taxonomy_path is not None and _CODE.fullmatch(self.taxonomy_path) is None:
            raise ValueError("draft_specification_taxonomy_invalid")
        _bounded(self.label, "draft_specification_label_invalid", 500)
        _bounded(self.value, "draft_specification_value_invalid")
        _bounded(self.raw_value, "draft_specification_raw_invalid", 100_000)
        if self.unit is not None:
            _bounded(self.unit, "draft_specification_unit_invalid", 40)
        _unique_evidence(self.evidence, "draft_specification_evidence_invalid")
        if self.taxonomy_path is None and not self.review.review_required:
            raise ValueError("draft_unmapped_specification_review_missing")

    def as_dict(self) -> dict[str, object]:
        return {
            "taxonomy_path": self.taxonomy_path,
            "label": self.label,
            "value": self.value,
            "raw_value": self.raw_value,
            "unit": self.unit,
            "evidence": [item.as_dict() for item in self.evidence],
            "review": self.review.as_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DraftSpecification:
        return cls(
            _optional_string(value, "taxonomy_path"),
            _required_string(value, "label"),
            _required_string(value, "value"),
            _required_string(value, "raw_value"),
            _optional_string(value, "unit"),
            _evidence(value, "evidence"),
            DraftReviewMetadata.from_dict(_mapping(value.get("review"), "draft_review_invalid")),
        )


@dataclass(frozen=True, slots=True)
class DraftModulePin:
    number: str | None
    name: str | None
    function: str
    evidence: tuple[EvidenceFragment, ...]

    def __post_init__(self) -> None:
        if self.number is None and self.name is None:
            raise ValueError("draft_module_pin_identity_missing")
        for name, item in (("number", self.number), ("name", self.name)):
            if item is not None:
                _bounded(item, f"draft_module_pin_{name}_invalid", 160)
        _bounded(self.function, "draft_module_pin_function_invalid", 2_000)
        _unique_evidence(self.evidence, "draft_module_pin_evidence_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "number": self.number,
            "name": self.name,
            "function": self.function,
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DraftModulePin:
        return cls(
            _optional_string(value, "number"),
            _optional_string(value, "name"),
            _required_string(value, "function"),
            _evidence(value, "evidence"),
        )


@dataclass(frozen=True, slots=True)
class DraftModuleConnection:
    instructions: tuple[DraftDescriptionSection, ...] = ()
    pins: tuple[DraftModulePin, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "instructions": [item.as_dict() for item in self.instructions],
            "pins": [item.as_dict() for item in self.pins],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DraftModuleConnection:
        return cls(
            tuple(
                DraftDescriptionSection.from_dict(
                    _mapping(item, "draft_connection_instruction_invalid")
                )
                for item in _object_list(value, "instructions")
            ),
            tuple(
                DraftModulePin.from_dict(_mapping(item, "draft_module_pin_invalid"))
                for item in _object_list(value, "pins")
            ),
        )


@dataclass(frozen=True, slots=True)
class DraftResource:
    label: str
    locator: str
    kind: ResourceKind
    evidence: tuple[EvidenceFragment, ...]

    def __post_init__(self) -> None:
        _bounded(self.label, "draft_resource_label_invalid", 500)
        _bounded(self.locator, "draft_resource_locator_invalid", 2_000)
        _unique_evidence(self.evidence, "draft_resource_evidence_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "locator": self.locator,
            "kind": self.kind.value,
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DraftResource:
        return cls(
            _required_string(value, "label"),
            _required_string(value, "locator"),
            ResourceKind(_required_string(value, "kind")),
            _evidence(value, "evidence"),
        )


@dataclass(frozen=True, slots=True)
class DraftInternalComponent:
    record_id: str
    name: str
    relation_type: ComponentSymbolRelationType
    status: DraftEnrichmentStatus
    confidence_basis_points: int
    evidence: tuple[EvidenceFragment, ...]
    review_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _bounded(self.record_id, "draft_internal_component_id_invalid", 1_000)
        _bounded(self.name, "draft_internal_component_name_invalid", 500)
        if not 0 <= self.confidence_basis_points <= 1_000:
            raise ValueError("draft_internal_component_confidence_invalid")
        _unique_evidence(self.evidence, "draft_internal_component_evidence_invalid")
        if self.status is DraftEnrichmentStatus.PROPOSED and not self.review_reasons:
            raise ValueError("draft_proposed_component_reasons_missing")
        if self.status is DraftEnrichmentStatus.ACCEPTED and self.review_reasons:
            raise ValueError("draft_accepted_component_reasons_forbidden")
        if any(not item.strip() or len(item) > 300 for item in self.review_reasons):
            raise ValueError("draft_internal_component_reason_invalid")
        if len(set(self.review_reasons)) != len(self.review_reasons):
            raise ValueError("draft_internal_component_reasons_duplicate")

    def as_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "name": self.name,
            "relation_type": self.relation_type.value,
            "status": self.status.value,
            "confidence_basis_points": self.confidence_basis_points,
            "evidence": [item.as_dict() for item in self.evidence],
            "review_reasons": list(self.review_reasons),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DraftInternalComponent:
        return cls(
            _required_string(value, "record_id"),
            _required_string(value, "name"),
            ComponentSymbolRelationType(_required_string(value, "relation_type")),
            DraftEnrichmentStatus(_required_string(value, "status")),
            _required_int(value, "confidence_basis_points"),
            _evidence(value, "evidence"),
            _string_list(value, "review_reasons"),
        )


@dataclass(frozen=True, slots=True)
class DraftKicadSymbol:
    record_id: str
    relation_type: ComponentSymbolRelationType
    status: DraftEnrichmentStatus
    confidence_basis_points: int
    library: str
    symbol_name: str
    description: str | None
    datasheet: str | None
    pins: tuple[KicadPin, ...]
    footprint_filters: tuple[str, ...]
    source_path: str
    source_revision: str
    source_content_sha256: str
    parser_version: str
    source_evidence: tuple[EvidenceFragment, ...]
    review_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for item, code, maximum in (
            (self.record_id, "draft_kicad_record_id_invalid", 1_000),
            (self.library, "draft_kicad_library_invalid", 300),
            (self.symbol_name, "draft_kicad_symbol_name_invalid", 500),
            (self.source_path, "draft_kicad_source_path_invalid", 1_000),
            (self.source_revision, "draft_kicad_source_revision_invalid", 160),
            (self.parser_version, "draft_kicad_parser_version_invalid", 40),
        ):
            _bounded(item, code, maximum)
        if not 0 <= self.confidence_basis_points <= 1_000:
            raise ValueError("draft_kicad_confidence_invalid")
        if _SHA256.fullmatch(self.source_content_sha256) is None:
            raise ValueError("draft_kicad_content_sha256_invalid")
        if self.description is not None:
            _bounded(self.description, "draft_kicad_description_invalid", 10_000)
        if self.datasheet is not None:
            _bounded(self.datasheet, "draft_kicad_datasheet_invalid", 2_000)
        _unique_evidence(self.source_evidence, "draft_kicad_source_evidence_invalid")
        if self.status is DraftEnrichmentStatus.PROPOSED and not self.review_reasons:
            raise ValueError("draft_proposed_kicad_reasons_missing")
        if self.status is DraftEnrichmentStatus.ACCEPTED and self.review_reasons:
            raise ValueError("draft_accepted_kicad_reasons_forbidden")
        if any(not item.strip() or len(item) > 300 for item in self.review_reasons):
            raise ValueError("draft_kicad_reason_invalid")
        if len(set(self.review_reasons)) != len(self.review_reasons):
            raise ValueError("draft_kicad_reasons_duplicate")

    def as_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "relation_type": self.relation_type.value,
            "status": self.status.value,
            "confidence_basis_points": self.confidence_basis_points,
            "library": self.library,
            "symbol_name": self.symbol_name,
            "description": self.description,
            "datasheet": self.datasheet,
            "pins": [item.as_dict() for item in self.pins],
            "footprint_filters": list(self.footprint_filters),
            "source_path": self.source_path,
            "source_revision": self.source_revision,
            "source_content_sha256": self.source_content_sha256,
            "parser_version": self.parser_version,
            "source_evidence": [item.as_dict() for item in self.source_evidence],
            "review_reasons": list(self.review_reasons),
            "pinout_level": "kicad_symbol",
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DraftKicadSymbol:
        if value.get("pinout_level") != "kicad_symbol":
            raise ValueError("draft_kicad_pinout_level_invalid")
        return cls(
            record_id=_required_string(value, "record_id"),
            relation_type=ComponentSymbolRelationType(_required_string(value, "relation_type")),
            status=DraftEnrichmentStatus(_required_string(value, "status")),
            confidence_basis_points=_required_int(value, "confidence_basis_points"),
            library=_required_string(value, "library"),
            symbol_name=_required_string(value, "symbol_name"),
            description=_optional_string(value, "description"),
            datasheet=_optional_string(value, "datasheet"),
            pins=tuple(
                KicadPin.from_dict(_mapping(item, "draft_kicad_pin_invalid"))
                for item in _object_list(value, "pins")
            ),
            footprint_filters=_string_list(value, "footprint_filters"),
            source_path=_required_string(value, "source_path"),
            source_revision=_required_string(value, "source_revision"),
            source_content_sha256=_required_string(value, "source_content_sha256"),
            parser_version=_required_string(value, "parser_version"),
            source_evidence=_evidence(value, "source_evidence"),
            review_reasons=_string_list(value, "review_reasons"),
        )


@dataclass(frozen=True, slots=True)
class CompositionInput:
    facts: NormalizedFacts
    identity: ComponentIdentity
    enrichments: tuple[EnrichmentCandidate, ...]
    quality_report: QualityReport

    def __post_init__(self) -> None:
        quality_input = QualityEvaluationInput(self.facts, self.identity, self.enrichments)
        if self.quality_report.input_sha256 != quality_input.input_sha256:
            raise ValueError("composition_quality_input_mismatch")
        if self.quality_report.profile is not self.facts.profile:
            raise ValueError("composition_quality_profile_mismatch")

    @property
    def input_sha256(self) -> str:
        payload = {
            "quality_report_sha256": sha256(self.quality_report.to_json().encode()).hexdigest(),
            "quality_input_sha256": self.quality_report.input_sha256,
        }
        return sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class ReviewDraft:
    SCHEMA_VERSION: ClassVar[str] = "review-draft/v1"

    input_sha256: str
    artifact: SourceArtifactMetadata
    composed_at: datetime
    composer_version: str
    quality_report_sha256: str
    quality_route: QualityRoute
    quality_score_basis_points: int
    title: DraftText
    aliases: tuple[DraftText, ...]
    manufacturer: DraftText | None
    selected_category: str | None
    summary: DraftText | None
    detailed_description: tuple[DraftDescriptionSection, ...]
    features: tuple[DraftText, ...]
    applications: tuple[DraftText, ...]
    module_specifications: tuple[DraftSpecification, ...]
    module_connection: DraftModuleConnection
    internal_electronic_components: tuple[DraftInternalComponent, ...]
    kicad_symbols: tuple[DraftKicadSymbol, ...]
    resources: tuple[DraftResource, ...]
    provenance: tuple[EvidenceFragment, ...]
    review_warnings: tuple[QualityIssue, ...]

    def __post_init__(self) -> None:
        for value, code in (
            (self.input_sha256, "review_draft_input_sha256_invalid"),
            (self.quality_report_sha256, "review_draft_quality_sha256_invalid"),
        ):
            if _SHA256.fullmatch(value) is None:
                raise ValueError(code)
        if self.composed_at.tzinfo is None or self.composed_at.utcoffset() is None:
            raise ValueError("review_draft_composed_at_must_be_aware")
        if _VERSION.fullmatch(self.composer_version) is None:
            raise ValueError("review_draft_composer_version_invalid")
        if not 0 <= self.quality_score_basis_points <= 1_000:
            raise ValueError("review_draft_quality_score_invalid")
        if self.quality_route is QualityRoute.REJECT:
            raise ValueError("review_draft_rejected_quality_forbidden")
        if self.selected_category is not None and _CODE.fullmatch(self.selected_category) is None:
            raise ValueError("review_draft_category_invalid")
        _unique_evidence(self.provenance, "review_draft_provenance_invalid")
        if any(item.source != self.artifact.source for item in self.provenance):
            raise ValueError("review_draft_provenance_source_mismatch")
        if not set(_review_draft_field_evidence(self)).issubset(self.provenance):
            raise ValueError("review_draft_field_provenance_missing")
        if len({item.record_id for item in self.kicad_symbols}) != len(self.kicad_symbols):
            raise ValueError("review_draft_kicad_duplicate")
        symbols = {item.record_id: item for item in self.kicad_symbols}
        if any(item.record_id not in symbols for item in self.internal_electronic_components):
            raise ValueError("review_draft_internal_component_symbol_missing")
        if any(
            (item.relation_type, item.status, item.confidence_basis_points)
            != (
                symbols[item.record_id].relation_type,
                symbols[item.record_id].status,
                symbols[item.record_id].confidence_basis_points,
            )
            for item in self.internal_electronic_components
        ):
            raise ValueError("review_draft_internal_component_relation_mismatch")
        warning_codes = [item.code for item in self.review_warnings]
        if len(warning_codes) != len(set(warning_codes)):
            raise ValueError("review_draft_warning_duplicate")
        if any(item.severity is QualityIssueSeverity.BLOCKING for item in self.review_warnings):
            raise ValueError("review_draft_blocking_warning_forbidden")
        if self.quality_route is QualityRoute.READY_TO_COMPOSE and any(
            item.severity is QualityIssueSeverity.WARNING for item in self.review_warnings
        ):
            raise ValueError("review_draft_ready_warning_forbidden")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "draft_status": "review_draft",
            "input_sha256": self.input_sha256,
            "artifact": self.artifact.as_dict(),
            "composed_at": self.composed_at.isoformat(),
            "composer_version": self.composer_version,
            "quality_report_sha256": self.quality_report_sha256,
            "quality_route": self.quality_route.value,
            "quality_score_basis_points": self.quality_score_basis_points,
            "title": self.title.as_dict(),
            "aliases": [item.as_dict() for item in self.aliases],
            "manufacturer": self.manufacturer.as_dict() if self.manufacturer else None,
            "selected_category": self.selected_category,
            "summary": self.summary.as_dict() if self.summary else None,
            "detailed_description": [item.as_dict() for item in self.detailed_description],
            "features": [item.as_dict() for item in self.features],
            "applications": [item.as_dict() for item in self.applications],
            "module_specifications": [item.as_dict() for item in self.module_specifications],
            "module_connection": self.module_connection.as_dict(),
            "internal_electronic_components": [
                item.as_dict() for item in self.internal_electronic_components
            ],
            "kicad_symbols": [item.as_dict() for item in self.kicad_symbols],
            "resources": [item.as_dict() for item in self.resources],
            "provenance": [item.as_dict() for item in self.provenance],
            "review_warnings": [item.as_dict() for item in self.review_warnings],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ReviewDraft:
        if value.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("review_draft_schema_version_unsupported")
        if value.get("draft_status") != "review_draft":
            raise ValueError("review_draft_status_invalid")
        composed_at = value.get("composed_at")
        if not isinstance(composed_at, str):
            raise ValueError("review_draft_composed_at_invalid")
        manufacturer = value.get("manufacturer")
        summary = value.get("summary")
        return cls(
            input_sha256=_required_string(value, "input_sha256"),
            artifact=SourceArtifactMetadata.from_dict(
                _mapping(value.get("artifact"), "review_draft_artifact_invalid")
            ),
            composed_at=datetime.fromisoformat(composed_at),
            composer_version=_required_string(value, "composer_version"),
            quality_report_sha256=_required_string(value, "quality_report_sha256"),
            quality_route=QualityRoute(_required_string(value, "quality_route")),
            quality_score_basis_points=_required_int(value, "quality_score_basis_points"),
            title=DraftText.from_dict(_mapping(value.get("title"), "review_draft_title_invalid")),
            aliases=tuple(
                DraftText.from_dict(_mapping(item, "review_draft_alias_invalid"))
                for item in _object_list(value, "aliases")
            ),
            manufacturer=(
                DraftText.from_dict(_mapping(manufacturer, "review_draft_manufacturer_invalid"))
                if manufacturer is not None
                else None
            ),
            selected_category=_optional_string(value, "selected_category"),
            summary=(
                DraftText.from_dict(_mapping(summary, "review_draft_summary_invalid"))
                if summary is not None
                else None
            ),
            detailed_description=tuple(
                DraftDescriptionSection.from_dict(
                    _mapping(item, "review_draft_description_invalid")
                )
                for item in _object_list(value, "detailed_description")
            ),
            features=tuple(
                DraftText.from_dict(_mapping(item, "review_draft_feature_invalid"))
                for item in _object_list(value, "features")
            ),
            applications=tuple(
                DraftText.from_dict(_mapping(item, "review_draft_application_invalid"))
                for item in _object_list(value, "applications")
            ),
            module_specifications=tuple(
                DraftSpecification.from_dict(_mapping(item, "review_draft_specification_invalid"))
                for item in _object_list(value, "module_specifications")
            ),
            module_connection=DraftModuleConnection.from_dict(
                _mapping(value.get("module_connection"), "review_draft_connection_invalid")
            ),
            internal_electronic_components=tuple(
                DraftInternalComponent.from_dict(
                    _mapping(item, "review_draft_internal_component_invalid")
                )
                for item in _object_list(value, "internal_electronic_components")
            ),
            kicad_symbols=tuple(
                DraftKicadSymbol.from_dict(_mapping(item, "review_draft_kicad_symbol_invalid"))
                for item in _object_list(value, "kicad_symbols")
            ),
            resources=tuple(
                DraftResource.from_dict(_mapping(item, "review_draft_resource_invalid"))
                for item in _object_list(value, "resources")
            ),
            provenance=_evidence(value, "provenance"),
            review_warnings=tuple(
                QualityIssue.from_dict(_mapping(item, "review_draft_warning_invalid"))
                for item in _object_list(value, "review_warnings")
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> ReviewDraft:
        decoded: object = json.loads(value)
        return cls.from_dict(_mapping(decoded, "review_draft_payload_invalid"))


def _review_draft_field_evidence(draft: ReviewDraft) -> tuple[EvidenceFragment, ...]:
    evidence = list(draft.title.evidence)
    if draft.manufacturer is not None:
        evidence.extend(draft.manufacturer.evidence)
    evidence.extend(item for alias in draft.aliases for item in alias.evidence)
    if draft.summary is not None:
        evidence.extend(draft.summary.evidence)
    evidence.extend(
        item for description in draft.detailed_description for item in description.evidence
    )
    evidence.extend(item for feature in draft.features for item in feature.evidence)
    evidence.extend(item for application in draft.applications for item in application.evidence)
    evidence.extend(
        item for specification in draft.module_specifications for item in specification.evidence
    )
    evidence.extend(
        item
        for instruction in draft.module_connection.instructions
        for item in instruction.evidence
    )
    evidence.extend(item for pin in draft.module_connection.pins for item in pin.evidence)
    evidence.extend(
        item for component in draft.internal_electronic_components for item in component.evidence
    )
    evidence.extend(item for resource in draft.resources for item in resource.evidence)
    evidence.extend(item for symbol in draft.kicad_symbols for item in symbol.source_evidence)
    return tuple(dict.fromkeys(evidence))
