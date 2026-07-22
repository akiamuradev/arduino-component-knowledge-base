"""Stage 4 semantic normalization contracts, properties and golden corpus."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.pipeline import (
    EvidenceFragment,
    ExtractedFacts,
    ExtractedField,
    FactNormalizer,
    ImportPipelineContext,
    NormalizationError,
    NormalizationProfile,
    NormalizedFacts,
    PipelineStage,
    RawSpecification,
    SeeedFactExtractor,
    SemanticFactNormalizer,
    SourceArtifact,
    SourceArtifactMetadata,
    SourceReference,
    StageExecution,
)
from arduino_component_kb.imports.pipeline.normalization import (
    SPECIFICATION_REGISTRY,
    ValueKind,
    normalize_interface,
    normalize_manufacturer,
    normalize_part_number,
    normalize_value,
)

FIXTURES = Path(__file__).parent / "fixtures" / "seeed"
GOLDEN = Path(__file__).parent / "golden" / "imports" / "seeed_normalization_v1.json"
REVISION = "a" * 40
STARTED_AT = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
SEEED_CASES = tuple(
    sorted(path.name for path in FIXTURES.iterdir() if path.suffix in {".md", ".mdx"})
)


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self._values = iter(values)

    def now(self) -> datetime:
        return next(self._values)


def artifact(file_name: str) -> SourceArtifact:
    content = (FIXTURES / file_name).read_bytes()
    return SourceArtifact(
        SourceArtifactMetadata(
            SourceReference(
                "seeed_wiki",
                SeeedWikiAdapter.repository_url,
                file_name,
                REVISION,
            ),
            "text/mdx" if file_name.endswith(".mdx") else "text/markdown",
            sha256(content).hexdigest(),
            len(content),
            STARTED_AT,
        ),
        content,
    )


def initial_context() -> ImportPipelineContext:
    return ImportPipelineContext(
        UUID("87654321-4321-6789-4321-678943216789"),
        "seeed_wiki",
        SeeedWikiAdapter.repository_url,
        "2.0.0",
        STARTED_AT,
    ).advance(StageExecution(PipelineStage.ACQUISITION, STARTED_AT, STARTED_AT))


async def extracted(file_name: str) -> tuple[ImportPipelineContext, ExtractedFacts]:
    result = await SeeedFactExtractor(
        SequenceClock(STARTED_AT + timedelta(seconds=1), STARTED_AT + timedelta(seconds=2))
    ).extract(initial_context(), artifact(file_name))
    return result.context, result.value


async def normalized(file_name: str) -> tuple[ImportPipelineContext, NormalizedFacts]:
    context, facts = await extracted(file_name)
    normalizer: FactNormalizer[ExtractedFacts, NormalizedFacts] = SemanticFactNormalizer(
        SequenceClock(STARTED_AT + timedelta(seconds=3), STARTED_AT + timedelta(seconds=4))
    )
    result = await normalizer.normalize(context, facts)
    assert result.stage is PipelineStage.NORMALIZATION
    assert result.context.next_stage is PipelineStage.IDENTITY
    return result.context, result.value


def projection(facts: NormalizedFacts) -> dict[str, object]:
    return {
        "payload_sha256": sha256(facts.to_json().encode()).hexdigest(),
        "input_sha256": facts.extracted_facts_sha256,
        "profile": facts.profile.value,
        "specifications": [
            {
                "path": item.taxonomy_path,
                "label": item.original_label,
                "original": item.trace.original_value,
                "normalized": item.trace.normalized_value,
                "unit": item.normalized_unit,
                "rule": item.trace.rule_id,
                "confidence": item.trace.confidence.value,
            }
            for item in facts.specifications
        ],
        "unmapped_specifications": [
            {
                "label": item.original_label,
                "value": item.original_value,
                "reason": item.reason,
            }
            for item in facts.unmapped_specifications
        ],
        "interfaces": [item.trace.normalized_value for item in facts.interfaces],
        "unmapped_interfaces": [item.trace.normalized_value for item in facts.unmapped_interfaces],
        "manufacturers": [item.trace.normalized_value for item in facts.manufacturers],
        "identifiers": [
            [item.kind.value, item.trace.normalized_value] for item in facts.identifiers
        ],
        "primary_ics": [
            [item.kind.value, item.trace.normalized_value] for item in facts.primary_ics
        ],
        "source_unmapped": [item.value.label for item in facts.source_unmapped_facts],
        "conflicts": [item.as_dict() for item in facts.conflicts],
        "warnings": list(facts.warnings),
    }


async def test_fifteen_profile_normalization_matches_golden() -> None:
    expected = cast(dict[str, dict[str, object]], json.loads(GOLDEN.read_text("utf-8")))
    actual = {file_name: projection((await normalized(file_name))[1]) for file_name in SEEED_CASES}

    assert len(actual) == 15
    assert actual == expected


@pytest.mark.parametrize(
    ("raw", "kind", "expected", "unit", "rule"),
    [
        ("3.3 to 5 volts", ValueKind.VOLTAGE, "3.3–5 V", "V", "quantity.voltage.range.v1"),
        ("20 milliamps", ValueKind.CURRENT, "20 mA", "mA", "quantity.current.scalar.v1"),
        (
            "-40 to 85 degrees celsius",
            ValueKind.TEMPERATURE,
            "-40–85 °C",
            "°C",
            "quantity.temperature.range.v1",
        ),
        ("3.3V to 5", ValueKind.VOLTAGE, "3.3–5 V", "V", "quantity.voltage.range.v1"),
        (
            "±0.5 degrees celsius",
            ValueKind.AUTO,
            "±0.5 °C",
            "°C",
            "quantity.temperature.tolerance.v1",
        ),
        ("16MHz", ValueKind.FREQUENCY, "16 MHz", "MHz", "quantity.frequency.scalar.v1"),
        ("21 x 17.8 millimeters", ValueKind.DIMENSIONS, "21 × 17.8 mm", "mm", "dimensions.axes.v1"),
        (
            "300 to 1100 hPa",
            ValueKind.PRESSURE,
            "300–1100 hPa",
            "hPa",
            "quantity.pressure.range.v1",
        ),
    ],
)
def test_value_rules_are_explicit_and_versionable(
    raw: str, kind: ValueKind, expected: str, unit: str, rule: str
) -> None:
    result = normalize_value(raw, kind)

    assert result.value == expected
    assert result.unit == unit
    assert result.rule_id == rule


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("I²C", ("I2C",)),
        ("SPI / UART", ("SPI", "UART")),
        ("analog and digital", ("analog", "digital")),
        ("Wi-Fi and Bluetooth", ("Wi-Fi", "Bluetooth")),
    ],
)
def test_interface_aliases_are_deterministic(raw: str, expected: tuple[str, ...]) -> None:
    assert tuple(item.value for item in normalize_interface(raw)) == expected


@pytest.mark.parametrize("alias", ["Seeed", "seeedstudio", "Seeed Technology Co. Ltd."])
def test_manufacturer_aliases_keep_a_traceable_canonical_value(alias: str) -> None:
    result = normalize_manufacturer(alias)

    assert result.value == "Seeed Studio"
    assert result.rule_id == "manufacturer.aliases.v1"


def test_part_number_alias_rule_normalizes_case_and_unicode_dashes() -> None:
    result = normalize_part_number(" esp32–c3 ")

    assert result.value == "ESP32-C3"
    assert result.rule_id == "part-number.ascii-case.v1"


@given(
    value=st.integers(min_value=0, max_value=100_000),
    unit=st.sampled_from(["V", "volt", "volts"]),
    left_space=st.integers(min_value=0, max_value=4),
    right_space=st.integers(min_value=0, max_value=4),
)
def test_voltage_scalar_property_is_whitespace_and_alias_stable(
    value: int, unit: str, left_space: int, right_space: int
) -> None:
    raw = f"{' ' * left_space}{value}{' ' * right_space}{unit}"
    result = normalize_value(raw, ValueKind.VOLTAGE)

    assert result.value == f"{value} V"
    assert result.unit == "V"


@given(
    first=st.integers(min_value=-1000, max_value=1000),
    second=st.integers(min_value=-1000, max_value=1000),
    separator=st.sampled_from([" to ", "-", "–", "~"]),
    unit=st.sampled_from(["mA", "milliamps", "milliamperes"]),
)
def test_current_range_property_preserves_bounds_and_is_idempotent(
    first: int, second: int, separator: str, unit: str
) -> None:
    result = normalize_value(f"{first}{separator}{second} {unit}", ValueKind.CURRENT)
    repeated = normalize_value(result.value, ValueKind.CURRENT)

    assert result.value == f"{first}–{second} mA"
    assert repeated.value == result.value


async def test_profile_aware_aliases_choose_different_taxonomy_paths() -> None:
    sensor = (await normalized("environmental_sensor.md"))[1]
    display = (await normalized("display_spi.md"))[1]
    actuator = (await normalized("motor_shield.md"))[1]
    board = (await normalized("development_board.md"))[1]
    communication = (await normalized("communication_module.md"))[1]

    assert sensor.profile is NormalizationProfile.SENSOR
    assert "sensor.temperature.measurement_range" in {
        item.taxonomy_path for item in sensor.specifications
    }
    assert display.profile is NormalizationProfile.DISPLAY
    assert "display.resolution" in {item.taxonomy_path for item in display.specifications}
    assert actuator.profile is NormalizationProfile.ACTUATOR
    assert "actuator.current.maximum_output" in {
        item.taxonomy_path for item in actuator.specifications
    }
    assert board.profile is NormalizationProfile.BOARD
    assert "board.processor" in {item.taxonomy_path for item in board.specifications}
    assert communication.profile is NormalizationProfile.COMMUNICATION
    assert "communication.frequency.carrier" in {
        item.taxonomy_path for item in communication.specifications
    }


async def test_unknown_specification_and_source_unmapped_sections_are_never_lost() -> None:
    _, result = await normalized("minimal_no_summary.md")

    assert [
        (item.original_label, item.original_value) for item in result.unmapped_specifications
    ] == [("Vendor tuning code", "X-17")]
    assert [item.value.label for item in result.source_unmapped_facts] == ["Prototype Notes"]
    assert result.warnings == ("unmapped_specification",)


async def test_conflicting_values_from_different_sections_are_visible() -> None:
    context, facts = await extracted("actuator_module.md")
    source = facts.artifact.source
    conflict = ExtractedField(
        RawSpecification("Supply voltage", "12 V"),
        "| Supply voltage | 12 V |",
        (
            EvidenceFragment(
                source,
                "| Supply voltage | 12 V |",
                "markdown.key-value-v1",
                "2.0.0",
                selector="line[99]",
                section="Electrical Notes",
            ),
        ),
    )
    changed = replace(facts, specifications=(*facts.specifications, conflict))
    result = await SemanticFactNormalizer(
        SequenceClock(STARTED_AT + timedelta(seconds=3), STARTED_AT + timedelta(seconds=4))
    ).normalize(context, changed)

    assert result.value.conflicts[0].taxonomy_path == "electrical.voltage.supply"
    assert result.value.conflicts[0].normalized_values == ("2.75–6.8 V", "12 V")
    assert "normalization_conflict" in result.value.warnings


async def test_normalized_facts_round_trip_and_input_immutability() -> None:
    _, source = await extracted("connector_module.md")
    before = source.to_json()
    context = initial_context().advance(
        StageExecution(
            PipelineStage.EXTRACTION,
            STARTED_AT + timedelta(seconds=1),
            STARTED_AT + timedelta(seconds=2),
        )
    )
    result = await SemanticFactNormalizer(
        SequenceClock(STARTED_AT + timedelta(seconds=3), STARTED_AT + timedelta(seconds=4))
    ).normalize(context, source)

    restored = NormalizedFacts.from_json(result.value.to_json())
    assert restored == result.value
    assert source.to_json() == before
    assert restored.extracted_facts == source
    assert restored.extracted_facts.module_pinout == source.module_pinout
    assert restored.extracted_facts.resources == source.resources
    assert all(item.trace.raw_value for item in result.value.specifications)


async def test_normalized_facts_are_not_a_composed_catalogue_card() -> None:
    _, result = await normalized("complete.md")

    assert set(result.as_dict()).isdisjoint(
        {"name", "title", "summary", "description", "category", "publication_status"}
    )


async def test_normalizer_rejects_out_of_order_context() -> None:
    _, facts = await extracted("complete.md")
    normalizer = SemanticFactNormalizer(SequenceClock(STARTED_AT + timedelta(seconds=3)))

    with pytest.raises(NormalizationError, match="normalization_stage_out_of_order"):
        await normalizer.normalize(initial_context(), facts)


def test_taxonomy_is_hierarchical_and_aliases_are_profile_scoped() -> None:
    assert "electrical.voltage" in SPECIFICATION_REGISTRY.taxonomy_branches()
    assert "sensor.temperature" in SPECIFICATION_REGISTRY.taxonomy_branches()
    display = SPECIFICATION_REGISTRY.resolve("Resolution", NormalizationProfile.DISPLAY)
    generic = SPECIFICATION_REGISTRY.resolve("Resolution", NormalizationProfile.GENERIC)
    assert display is not None and display.taxonomy_path == "display.resolution"
    assert generic is not None and generic.taxonomy_path == "measurement.resolution"
