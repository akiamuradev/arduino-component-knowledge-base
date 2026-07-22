"""Raw, evidenced facts produced before semantic normalization or card composition."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from arduino_component_kb.imports.pipeline.models.provenance import (
    EvidenceFragment,
    ExtractionWarning,
    SourceArtifactMetadata,
)

_IDENTIFIER_VALUE = re.compile(r"^[^\x00\r\n]{1,300}$")


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


def _bounded_text(value: str, code: str, maximum: int = 100_000) -> str:
    if not value.strip() or "\x00" in value or len(value) > maximum:
        raise ValueError(code)
    return value


def _decode_string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("extracted_string_value_invalid")
    return value


@dataclass(frozen=True, slots=True)
class ExtractedField[ValueT]:
    value: ValueT
    raw_value: str
    evidence: tuple[EvidenceFragment, ...]

    def __post_init__(self) -> None:
        _bounded_text(self.raw_value, "extracted_field_raw_value_invalid")
        if isinstance(self.value, str):
            _bounded_text(self.value, "extracted_field_value_invalid")
        if not self.evidence:
            raise ValueError("extracted_field_evidence_missing")

    def as_dict(self, encode_value: Callable[[ValueT], object]) -> dict[str, object]:
        return {
            "value": encode_value(self.value),
            "raw_value": self.raw_value,
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, object], decode_value: Callable[[object], ValueT]
    ) -> ExtractedField[ValueT]:
        return cls(
            value=decode_value(value.get("value")),
            raw_value=_required_string(value, "raw_value"),
            evidence=tuple(
                EvidenceFragment.from_dict(_mapping(item, "extracted_field_evidence_invalid"))
                for item in _object_list(value, "evidence")
            ),
        )


@dataclass(frozen=True, slots=True)
class DescriptionSection:
    heading: str | None
    body: str

    def __post_init__(self) -> None:
        if self.heading is not None:
            _bounded_text(self.heading, "description_heading_invalid", 500)
        _bounded_text(self.body, "description_body_invalid")

    def as_dict(self) -> dict[str, object]:
        return {"heading": self.heading, "body": self.body}

    @classmethod
    def from_value(cls, value: object) -> DescriptionSection:
        item = _mapping(value, "description_section_invalid")
        return cls(
            heading=_optional_string(item, "heading"),
            body=_required_string(item, "body"),
        )


class IdentifierKind(StrEnum):
    SKU = "sku"
    MODEL = "model"
    PART_NUMBER = "part_number"
    PRODUCT_ID = "product_id"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Identifier:
    kind: IdentifierKind
    value: str

    def __post_init__(self) -> None:
        if _IDENTIFIER_VALUE.fullmatch(self.value) is None:
            raise ValueError("identifier_value_invalid")

    def as_dict(self) -> dict[str, object]:
        return {"kind": self.kind.value, "value": self.value}

    @classmethod
    def from_value(cls, value: object) -> Identifier:
        item = _mapping(value, "identifier_invalid")
        return cls(
            kind=IdentifierKind(_required_string(item, "kind")),
            value=_required_string(item, "value"),
        )


@dataclass(frozen=True, slots=True)
class ModulePin:
    number: str | None
    name: str | None
    function: str

    def __post_init__(self) -> None:
        if self.number is None and self.name is None:
            raise ValueError("module_pin_identity_missing")
        for field_name, value in (("number", self.number), ("name", self.name)):
            if value is not None:
                _bounded_text(value, f"module_pin_{field_name}_invalid", 160)
        _bounded_text(self.function, "module_pin_function_invalid", 2_000)

    def as_dict(self) -> dict[str, object]:
        return {"number": self.number, "name": self.name, "function": self.function}

    @classmethod
    def from_value(cls, value: object) -> ModulePin:
        item = _mapping(value, "module_pin_invalid")
        return cls(
            number=_optional_string(item, "number"),
            name=_optional_string(item, "name"),
            function=_required_string(item, "function"),
        )


@dataclass(frozen=True, slots=True)
class RawSpecification:
    label: str
    value: str

    def __post_init__(self) -> None:
        _bounded_text(self.label, "raw_specification_label_invalid", 500)
        _bounded_text(self.value, "raw_specification_value_invalid", 10_000)

    def as_dict(self) -> dict[str, object]:
        return {"label": self.label, "value": self.value}

    @classmethod
    def from_value(cls, value: object) -> RawSpecification:
        item = _mapping(value, "raw_specification_invalid")
        return cls(
            label=_required_string(item, "label"),
            value=_required_string(item, "value"),
        )


class ResourceKind(StrEnum):
    DATASHEET = "datasheet"
    LIBRARY = "library"
    SCHEMATIC = "schematic"
    EXAMPLE = "example"
    DOCUMENTATION = "documentation"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ResourceReference:
    label: str
    locator: str
    kind: ResourceKind = ResourceKind.OTHER

    def __post_init__(self) -> None:
        _bounded_text(self.label, "resource_label_invalid", 500)
        _bounded_text(self.locator, "resource_locator_invalid", 2_000)

    def as_dict(self) -> dict[str, object]:
        return {"label": self.label, "locator": self.locator, "kind": self.kind.value}

    @classmethod
    def from_value(cls, value: object) -> ResourceReference:
        item = _mapping(value, "resource_reference_invalid")
        return cls(
            label=_required_string(item, "label"),
            locator=_required_string(item, "locator"),
            kind=ResourceKind(_required_string(item, "kind")),
        )


@dataclass(frozen=True, slots=True)
class ImageReference:
    locator: str
    alt_text: str | None = None

    def __post_init__(self) -> None:
        _bounded_text(self.locator, "image_locator_invalid", 2_000)
        if self.alt_text is not None:
            _bounded_text(self.alt_text, "image_alt_text_invalid", 1_000)

    def as_dict(self) -> dict[str, object]:
        return {"locator": self.locator, "alt_text": self.alt_text}

    @classmethod
    def from_value(cls, value: object) -> ImageReference:
        item = _mapping(value, "image_reference_invalid")
        return cls(
            locator=_required_string(item, "locator"),
            alt_text=_optional_string(item, "alt_text"),
        )


@dataclass(frozen=True, slots=True)
class UnknownFact:
    label: str
    value: str

    def __post_init__(self) -> None:
        _bounded_text(self.label, "unknown_fact_label_invalid", 500)
        _bounded_text(self.value, "unknown_fact_value_invalid", 100_000)

    def as_dict(self) -> dict[str, object]:
        return {"label": self.label, "value": self.value}

    @classmethod
    def from_value(cls, value: object) -> UnknownFact:
        item = _mapping(value, "unknown_fact_invalid")
        return cls(
            label=_required_string(item, "label"),
            value=_required_string(item, "value"),
        )


def _encode_fields[ValueT](
    fields: tuple[ExtractedField[ValueT], ...], encoder: Callable[[ValueT], object]
) -> list[dict[str, object]]:
    return [field.as_dict(encoder) for field in fields]


def _decode_fields[ValueT](
    value: Mapping[str, object], key: str, decoder: Callable[[object], ValueT]
) -> tuple[ExtractedField[ValueT], ...]:
    return tuple(
        ExtractedField.from_dict(_mapping(item, f"{key}_field_invalid"), decoder)
        for item in _object_list(value, key)
    )


def _identity(value: str) -> object:
    return value


@dataclass(frozen=True, slots=True)
class ExtractedFacts:
    SCHEMA_VERSION: ClassVar[str] = "extracted-facts/v1"

    artifact: SourceArtifactMetadata
    title_candidates: tuple[ExtractedField[str], ...] = ()
    summary_candidates: tuple[ExtractedField[str], ...] = ()
    description_sections: tuple[ExtractedField[DescriptionSection], ...] = ()
    feature_facts: tuple[ExtractedField[str], ...] = ()
    application_facts: tuple[ExtractedField[str], ...] = ()
    usage_sections: tuple[ExtractedField[DescriptionSection], ...] = ()
    identifiers: tuple[ExtractedField[Identifier], ...] = ()
    manufacturer_candidates: tuple[ExtractedField[str], ...] = ()
    brand_candidates: tuple[ExtractedField[str], ...] = ()
    interface_facts: tuple[ExtractedField[str], ...] = ()
    module_pinout: tuple[ExtractedField[ModulePin], ...] = ()
    primary_ic_candidates: tuple[ExtractedField[Identifier], ...] = ()
    specifications: tuple[ExtractedField[RawSpecification], ...] = ()
    resources: tuple[ExtractedField[ResourceReference], ...] = ()
    images: tuple[ExtractedField[ImageReference], ...] = ()
    unmapped_facts: tuple[ExtractedField[UnknownFact], ...] = ()
    warnings: tuple[ExtractionWarning, ...] = ()

    def __post_init__(self) -> None:
        self._validate_sources(self.title_candidates)
        self._validate_sources(self.summary_candidates)
        self._validate_sources(self.description_sections)
        self._validate_sources(self.feature_facts)
        self._validate_sources(self.application_facts)
        self._validate_sources(self.usage_sections)
        self._validate_sources(self.identifiers)
        self._validate_sources(self.manufacturer_candidates)
        self._validate_sources(self.brand_candidates)
        self._validate_sources(self.interface_facts)
        self._validate_sources(self.module_pinout)
        self._validate_sources(self.primary_ic_candidates)
        self._validate_sources(self.specifications)
        self._validate_sources(self.resources)
        self._validate_sources(self.images)
        self._validate_sources(self.unmapped_facts)
        for warning in self.warnings:
            if any(evidence.source != self.artifact.source for evidence in warning.evidence):
                raise ValueError("extraction_warning_source_mismatch")

    def _validate_sources[ValueT](self, fields: tuple[ExtractedField[ValueT], ...]) -> None:
        if any(
            evidence.source != self.artifact.source
            for field in fields
            for evidence in field.evidence
        ):
            raise ValueError("extracted_field_source_mismatch")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "artifact": self.artifact.as_dict(),
            "title_candidates": _encode_fields(self.title_candidates, _identity),
            "summary_candidates": _encode_fields(self.summary_candidates, _identity),
            "description_sections": _encode_fields(
                self.description_sections, lambda value: value.as_dict()
            ),
            "feature_facts": _encode_fields(self.feature_facts, _identity),
            "application_facts": _encode_fields(self.application_facts, _identity),
            "usage_sections": _encode_fields(self.usage_sections, lambda value: value.as_dict()),
            "identifiers": _encode_fields(self.identifiers, lambda value: value.as_dict()),
            "manufacturer_candidates": _encode_fields(self.manufacturer_candidates, _identity),
            "brand_candidates": _encode_fields(self.brand_candidates, _identity),
            "interface_facts": _encode_fields(self.interface_facts, _identity),
            "module_pinout": _encode_fields(self.module_pinout, lambda value: value.as_dict()),
            "primary_ic_candidates": _encode_fields(
                self.primary_ic_candidates, lambda value: value.as_dict()
            ),
            "specifications": _encode_fields(self.specifications, lambda value: value.as_dict()),
            "resources": _encode_fields(self.resources, lambda value: value.as_dict()),
            "images": _encode_fields(self.images, lambda value: value.as_dict()),
            "unmapped_facts": _encode_fields(self.unmapped_facts, lambda value: value.as_dict()),
            "warnings": [warning.as_dict() for warning in self.warnings],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ExtractedFacts:
        if value.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("extracted_facts_schema_version_unsupported")
        return cls(
            artifact=SourceArtifactMetadata.from_dict(
                _mapping(value.get("artifact"), "extracted_facts_artifact_invalid")
            ),
            title_candidates=_decode_fields(value, "title_candidates", _decode_string),
            summary_candidates=_decode_fields(value, "summary_candidates", _decode_string),
            description_sections=_decode_fields(
                value, "description_sections", DescriptionSection.from_value
            ),
            feature_facts=_decode_fields(value, "feature_facts", _decode_string),
            application_facts=_decode_fields(value, "application_facts", _decode_string),
            usage_sections=_decode_fields(value, "usage_sections", DescriptionSection.from_value),
            identifiers=_decode_fields(value, "identifiers", Identifier.from_value),
            manufacturer_candidates=_decode_fields(
                value, "manufacturer_candidates", _decode_string
            ),
            brand_candidates=_decode_fields(value, "brand_candidates", _decode_string),
            interface_facts=_decode_fields(value, "interface_facts", _decode_string),
            module_pinout=_decode_fields(value, "module_pinout", ModulePin.from_value),
            primary_ic_candidates=_decode_fields(
                value, "primary_ic_candidates", Identifier.from_value
            ),
            specifications=_decode_fields(value, "specifications", RawSpecification.from_value),
            resources=_decode_fields(value, "resources", ResourceReference.from_value),
            images=_decode_fields(value, "images", ImageReference.from_value),
            unmapped_facts=_decode_fields(value, "unmapped_facts", UnknownFact.from_value),
            warnings=tuple(
                ExtractionWarning.from_dict(_mapping(item, "extraction_warning_invalid"))
                for item in _object_list(value, "warnings")
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> ExtractedFacts:
        decoded: object = json.loads(value)
        return cls.from_dict(_mapping(decoded, "extracted_facts_payload_invalid"))
