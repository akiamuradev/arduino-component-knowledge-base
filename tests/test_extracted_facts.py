"""Domain contract tests for raw, evidenced extraction results."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from arduino_component_kb.imports.pipeline import (
    DescriptionSection,
    EvidenceFragment,
    ExtractedFacts,
    ExtractedField,
    ExtractionWarning,
    Identifier,
    IdentifierKind,
    ImageReference,
    ModulePin,
    RawSpecification,
    ResourceKind,
    ResourceReference,
    SourceArtifactMetadata,
    SourceReference,
    UnknownFact,
)


def source() -> SourceReference:
    return SourceReference(
        source_key="seeed_wiki",
        source_url="https://github.com/Seeed-Studio/wiki-documents",
        source_path="sites/en/docs/Sensor/Grove-Temperature-Sensor.md",
        source_revision="a" * 40,
    )


def evidence(raw_text: str, section: str, *, selector: str | None = None) -> EvidenceFragment:
    return EvidenceFragment(
        source=source(),
        selector=selector,
        section=section,
        raw_text=raw_text,
        extraction_method="markdown.section-v1",
        parser_version="2.0.0-dev1",
    )


def field[ValueT](
    value: ValueT,
    raw_value: str,
    section: str,
    *,
    selector: str | None = None,
) -> ExtractedField[ValueT]:
    return ExtractedField(
        value=value,
        raw_value=raw_value,
        evidence=(evidence(raw_value, section, selector=selector),),
    )


def sample_facts() -> ExtractedFacts:
    artifact = SourceArtifactMetadata(
        source=source(),
        media_type="text/markdown",
        content_sha256="b" * 64,
        byte_length=4_096,
        acquired_at=datetime(2026, 7, 23, 10, 0, tzinfo=UTC),
    )
    return ExtractedFacts(
        artifact=artifact,
        title_candidates=(
            field(
                "Grove - Temperature Sensor",
                "title: Grove - Temperature Sensor",
                "frontmatter",
                selector="frontmatter.title",
            ),
        ),
        summary_candidates=(
            field(
                "A Grove module for measuring ambient temperature.",
                "description: A Grove module for measuring ambient temperature.",
                "frontmatter",
                selector="frontmatter.description",
            ),
        ),
        description_sections=(
            field(
                DescriptionSection(
                    heading="Introduction",
                    body="The module exposes an analog signal proportional to temperature.",
                ),
                "## Introduction\nThe module exposes an analog signal proportional to temperature.",
                "Introduction",
            ),
        ),
        feature_facts=(field("Low power consumption", "- Low power consumption", "Features"),),
        application_facts=(
            field("Classroom weather station", "- Classroom weather station", "Applications"),
        ),
        usage_sections=(
            field(
                DescriptionSection(
                    heading="Getting Started",
                    body="Connect SIG to an analog input.",
                ),
                "## Getting Started\nConnect SIG to an analog input.",
                "Getting Started",
            ),
        ),
        identifiers=(
            field(
                Identifier(IdentifierKind.SKU, "101020015"),
                "SKU: 101020015",
                "Product data",
            ),
        ),
        manufacturer_candidates=(
            field("Seeed Studio", "Manufacturer: Seeed Studio", "Product data"),
        ),
        brand_candidates=(field("Grove", "Brand: Grove", "Product data"),),
        interface_facts=(field("Analog", "Interface: Analog", "Specifications"),),
        module_pinout=(
            field(
                ModulePin(number="1", name="SIG", function="Analog signal output"),
                "| 1 | SIG | Analog signal output |",
                "Pinout",
                selector="table[1] row[1]",
            ),
        ),
        primary_ic_candidates=(
            field(
                Identifier(IdentifierKind.PART_NUMBER, "NTC-MF52"),
                "Built around an NTC-MF52 thermistor",
                "Hardware Overview",
            ),
        ),
        specifications=(
            field(
                RawSpecification("Supply Voltage", "3.3V to 5V"),
                "| Supply Voltage | 3.3V to 5V |",
                "Specifications",
                selector="table[1] row[1]",
            ),
            field(
                RawSpecification("Signal settling profile", "fast/typical"),
                "| Signal settling profile | fast/typical |",
                "Specifications",
                selector="table[1] row[2]",
            ),
        ),
        resources=(
            field(
                ResourceReference(
                    label="Datasheet",
                    locator="https://files.seeedstudio.com/example.pdf",
                    kind=ResourceKind.DATASHEET,
                ),
                "[Datasheet](https://files.seeedstudio.com/example.pdf)",
                "Resources",
            ),
        ),
        images=(
            field(
                ImageReference(
                    locator="https://files.seeedstudio.com/product.png",
                    alt_text="Temperature module",
                ),
                "![Temperature module](https://files.seeedstudio.com/product.png)",
                "Introduction",
            ),
        ),
        unmapped_facts=(
            field(
                UnknownFact("Calibration matrix", "A1,B2,C3"),
                "Calibration matrix: A1,B2,C3",
                "Factory Notes",
            ),
        ),
        warnings=(
            ExtractionWarning(
                code="ambiguous_primary_ic",
                message="The page mentions more than one possible sensing element.",
                evidence=(
                    evidence(
                        "Built around an NTC-MF52 thermistor",
                        "Hardware Overview",
                    ),
                ),
            ),
        ),
    )


def test_extracted_facts_json_round_trip_is_stable_and_equal() -> None:
    facts = sample_facts()

    first = facts.to_json()
    restored = ExtractedFacts.from_json(first)

    assert restored == facts
    assert restored.to_json() == first
    assert json.loads(first)["schema_version"] == "extracted-facts/v1"


def test_unknown_specifications_and_unmapped_facts_survive_round_trip() -> None:
    restored = ExtractedFacts.from_json(sample_facts().to_json())

    unknown_specification = restored.specifications[1]
    assert unknown_specification.value == RawSpecification(
        "Signal settling profile", "fast/typical"
    )
    assert unknown_specification.raw_value == ("| Signal settling profile | fast/typical |")
    assert restored.unmapped_facts[0].value == UnknownFact("Calibration matrix", "A1,B2,C3")
    assert restored.unmapped_facts[0].evidence[0].section == "Factory Notes"


def test_extracted_payload_has_raw_evidence_but_no_normalized_or_card_fields() -> None:
    payload = sample_facts().as_dict()
    serialized = sample_facts().to_json()

    assert set(payload) == {
        "schema_version",
        "artifact",
        "title_candidates",
        "summary_candidates",
        "description_sections",
        "feature_facts",
        "application_facts",
        "usage_sections",
        "identifiers",
        "manufacturer_candidates",
        "brand_candidates",
        "interface_facts",
        "module_pinout",
        "primary_ic_candidates",
        "specifications",
        "resources",
        "images",
        "unmapped_facts",
        "warnings",
    }
    assert '"raw_value"' in serialized
    assert '"raw_text"' in serialized
    assert '"normalized_value"' not in serialized
    assert '"category_id"' not in serialized
    assert '"draft_status"' not in serialized


def test_every_fact_requires_evidence() -> None:
    with pytest.raises(ValueError, match="extracted_field_evidence_missing"):
        ExtractedField(value="orphan", raw_value="orphan", evidence=())


def test_evidence_requires_a_selector_or_section() -> None:
    with pytest.raises(ValueError, match="evidence_location_missing"):
        EvidenceFragment(
            source=source(),
            raw_text="orphan evidence",
            extraction_method="markdown.section-v1",
            parser_version="2.0.0-dev1",
        )


def test_fact_evidence_must_reference_the_artifact_source() -> None:
    facts = sample_facts()
    foreign_source = replace(source(), source_path="sites/en/docs/other.md")
    foreign_evidence = replace(facts.title_candidates[0].evidence[0], source=foreign_source)
    foreign_title = replace(facts.title_candidates[0], evidence=(foreign_evidence,))

    with pytest.raises(ValueError, match="extracted_field_source_mismatch"):
        replace(facts, title_candidates=(foreign_title,))


def test_source_artifact_rejects_naive_time_and_invalid_digest() -> None:
    with pytest.raises(ValueError, match="sha256_invalid"):
        SourceArtifactMetadata(
            source=source(),
            media_type="text/markdown",
            content_sha256="not-a-digest",
            byte_length=1,
            acquired_at=datetime(2026, 7, 23, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="timezone_aware"):
        SourceArtifactMetadata(
            source=source(),
            media_type="text/markdown",
            content_sha256="a" * 64,
            byte_length=1,
            acquired_at=datetime(2026, 7, 23),
        )


def test_unknown_schema_version_is_rejected() -> None:
    payload = sample_facts().as_dict()
    payload["schema_version"] = "extracted-facts/v999"

    with pytest.raises(ValueError, match="schema_version_unsupported"):
        ExtractedFacts.from_dict(payload)
