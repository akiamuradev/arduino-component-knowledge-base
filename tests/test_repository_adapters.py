"""Repository parser contracts, tolerant fixtures and non-execution guarantees."""

from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from arduino_component_kb.imports.adapters.kicad_symbols import KicadSymbolsAdapter
from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.dry_run import dry_run
from arduino_component_kb.imports.repository_domain import (
    ParseStatus,
    RepositoryEntry,
    RepositorySnapshot,
)

FIXTURES = Path(__file__).parent / "fixtures"
REVISION = "a" * 40


def snapshot(source: str, *names: str, revision: str = REVISION) -> RepositorySnapshot:
    root = FIXTURES / source
    repository = (
        SeeedWikiAdapter.repository_url if source == "seeed" else KicadSymbolsAdapter.repository_url
    )
    return RepositorySnapshot(
        repository,
        revision,
        {name: root.joinpath(name).read_bytes() for name in names},
    )


async def test_seeed_complete_document_has_license_provenance_and_no_code() -> None:
    adapter = SeeedWikiAdapter()
    source = snapshot("seeed", "complete.md")
    parsed = await adapter.parse_entry(
        source,
        RepositoryEntry("complete.md"),
        parsed_at=datetime(2026, 7, 16, tzinfo=UTC),
    )

    assert parsed.status is ParseStatus.PARSED
    assert parsed.draft_status == "draft"
    assert parsed.license_snapshot.spdx == "GPL-3.0-only"
    assert parsed.normalized_fields["title"] == "Grove - Temperature Sensor"
    specifications = parsed.normalized_fields["specifications"]
    assert isinstance(specifications, list)
    assert "125 °C" in str(specifications)
    assert {item["key"] for item in specifications if isinstance(item, dict)} == {
        "accuracy",
        "connector",
        "measurement-range",
        "operating-current",
        "supply-voltage",
    }
    assert parsed.normalized_fields["category_hint"] == "sensors"
    assert set(parsed.normalized_fields) == set(parsed.provenance)
    rendered = str(parsed.as_dict())
    assert "system(" not in rendered
    assert "image.png" not in rendered
    assert parsed.idempotency_key.startswith("repo-v1:")


@pytest.mark.parametrize(
    ("file_name", "expected_status", "warning"),
    [
        ("without_specifications.md", ParseStatus.PARSED, None),
        ("alternative_headings.mdx", ParseStatus.PARSED, None),
        ("broken_frontmatter.mdx", ParseStatus.PARSED_WITH_WARNINGS, "frontmatter_unterminated"),
        ("unknown_structure.md", ParseStatus.PARSED_WITH_WARNINGS, "unknown_section"),
    ],
)
async def test_seeed_tolerates_document_variants(
    file_name: str, expected_status: ParseStatus, warning: str | None
) -> None:
    source = snapshot("seeed", file_name)
    parsed = await SeeedWikiAdapter().parse_entry(
        source,
        RepositoryEntry(file_name),
        parsed_at=datetime.now(UTC),
    )
    assert parsed.status is expected_status
    if warning:
        assert any(item.startswith(warning) for item in parsed.warnings)
    assert "127.0.0.1" not in str(parsed.as_dict())
    assert set(parsed.normalized_fields) == set(parsed.provenance)


async def test_seeed_discovery_is_bounded_and_markdown_only() -> None:
    source = snapshot("seeed", "complete.md", "unknown_structure.md")
    entries = await SeeedWikiAdapter().discover(source, query="complete", limit=1)
    assert entries == (RepositoryEntry("complete.md", title="Grove - Temperature Sensor"),)


async def test_kicad_symbol_extracts_properties_filters_and_pins() -> None:
    adapter = KicadSymbolsAdapter()
    source = snapshot("kicad", "Sensor_Temperature.kicad_sym")
    parsed = await adapter.parse_entry(
        source,
        RepositoryEntry("Sensor_Temperature.kicad_sym", entry_name="LM35"),
        parsed_at=datetime.now(UTC),
        source_tag="10.0.0",
    )
    assert parsed.status is ParseStatus.PARSED
    assert parsed.license_snapshot.spdx == "CC-BY-SA-4.0"
    datasheet = parsed.normalized_fields["datasheet_url"]
    pins = parsed.normalized_fields["pins"]
    assert isinstance(datasheet, str) and datasheet.startswith("https://")
    assert isinstance(pins, list)
    assert parsed.normalized_fields["footprint_filters"] == ["TO?92*"]
    assert parsed.normalized_fields["category_hint"] == "sensors"
    assert len(pins) == 3
    assert set(parsed.normalized_fields) == set(parsed.provenance)


async def test_kicad_extends_and_multiple_units_are_preserved() -> None:
    source = snapshot("kicad", "MCU_Test.kicad_sym")
    parsed = await KicadSymbolsAdapter().parse_entry(
        source,
        RepositoryEntry("MCU_Test.kicad_sym", entry_name="ATmega328P"),
        parsed_at=datetime.now(UTC),
    )
    assert parsed.normalized_fields["extends"] == "ATmega8"
    assert parsed.normalized_fields["category_hint"] == "integrated-circuits"
    pins = parsed.normalized_fields["pins"]
    assert isinstance(pins, list)
    assert {pin["unit"] for pin in pins if isinstance(pin, dict)} == {1, 2}


async def test_kicad_missing_optional_datasheet_is_not_a_parse_failure() -> None:
    source = snapshot("kicad", "Relay_Missing_Datasheet.kicad_sym")
    parsed = await KicadSymbolsAdapter().parse_entry(
        source,
        RepositoryEntry("Relay_Missing_Datasheet.kicad_sym", entry_name="Relay_SPDT"),
        parsed_at=datetime.now(UTC),
    )
    assert parsed.status is ParseStatus.PARSED
    assert "datasheet_url" not in parsed.normalized_fields
    assert parsed.normalized_fields["category_hint"] == "actuators"


@pytest.mark.parametrize(
    ("title", "path", "expected"),
    [
        ("Grove - Relay", "sites/en/docs/Sensor/Grove/Actuator/Grove-Relay.md", "actuators"),
        ("Grove Button", "sites/en/docs/Sensor/Grove/Grove-Button.md", "input"),
        ("Grove OLED Display", "sites/en/docs/Sensor/Grove/OLED.md", "displays"),
        ("Grove Ultrasonic Ranger", "sites/en/docs/Sensor/Grove/Proximity/Ranger.md", "sensors"),
    ],
)
def test_seeed_category_prefers_component_identity_over_generic_parent_path(
    title: str, path: str, expected: str
) -> None:
    assert SeeedWikiAdapter()._category(title, path) == expected


async def test_seeed_rejects_markdown_noise_as_global_specifications() -> None:
    content = b"""---
title: Grove Light Sensor
description: A bounded light sensor example for parser regression tests.
---
# Grove Light Sensor
## Hardware Overview
| Property | Value |
| --- | --- |
| Operating voltage | 3.3~5 volts |
| Operating temperature | -10~60 degree C |
| Get ONE Now | [Buy](https://example.com) |
| !enter image description here | Raspberry pi |
"""
    source = RepositorySnapshot(
        SeeedWikiAdapter.repository_url,
        REVISION,
        {"sites/en/docs/Sensor/Grove-Light-Sensor.md": content},
    )

    parsed = await SeeedWikiAdapter().parse_entry(
        source,
        RepositoryEntry("sites/en/docs/Sensor/Grove-Light-Sensor.md"),
        parsed_at=datetime.now(UTC),
    )

    assert parsed.normalized_fields["specifications"] == [
        {"key": "operating-voltage", "label": "Operating voltage", "value": "3.3–5 V"},
        {
            "key": "operating-temperature",
            "label": "Operating temperature",
            "value": "-10–60 °C",
        },
    ]
    assert "untrusted_specification_ignored" in parsed.warnings


async def test_kicad_unknown_electrical_type_is_a_warning() -> None:
    source = snapshot("kicad", "Sensor_Unknown_Electrical.kicad_sym")
    parsed = await KicadSymbolsAdapter().parse_entry(
        source,
        RepositoryEntry("Sensor_Unknown_Electrical.kicad_sym", entry_name="FutureSensor"),
        parsed_at=datetime.now(UTC),
    )
    assert parsed.status is ParseStatus.PARSED_WITH_WARNINGS
    assert parsed.warnings == ("unknown_electrical_type:quantum",)


async def test_kicad_corruption_and_allowlist_are_typed_results() -> None:
    broken = snapshot("kicad", "Sensor_Broken.kicad_sym")
    broken_result = await KicadSymbolsAdapter().parse_entry(
        broken,
        RepositoryEntry("Sensor_Broken.kicad_sym", entry_name="Broken"),
        parsed_at=datetime.now(UTC),
    )
    assert broken_result.status is ParseStatus.INVALID_METADATA

    outside = snapshot("kicad", "Audio_Outside.kicad_sym")
    outside_result = await KicadSymbolsAdapter().parse_entry(
        outside,
        RepositoryEntry("Audio_Outside.kicad_sym", entry_name="AudioOnly"),
        parsed_at=datetime.now(UTC),
    )
    assert outside_result.status is ParseStatus.UNSUPPORTED_DOCUMENT


async def test_repository_identity_requires_registered_url_and_full_commit() -> None:
    with pytest.raises(ValueError, match="full_commit"):
        RepositorySnapshot(SeeedWikiAdapter.repository_url, "main", {"entry.md": b"# Entry"})
    foreign = RepositorySnapshot(
        "https://github.com/example/unregistered", REVISION, {"entry.md": b"# Entry"}
    )
    with pytest.raises(ValueError, match="repository_not_registered"):
        await SeeedWikiAdapter().discover(foreign)


def test_repository_adapter_modules_do_not_offer_process_execution() -> None:
    root = Path(__file__).parents[1] / "src" / "arduino_component_kb" / "imports" / "adapters"
    code = "\n".join(
        root.joinpath(name).read_text(encoding="utf-8")
        for name in ("seeed_wiki.py", "kicad_symbols.py", "sexpr.py", "markdown.py")
    )
    assert "subprocess" not in code
    assert "os.system" not in code
    assert "eval(" not in code
    assert "exec(" not in code


async def test_dry_run_emits_reviewable_draft_without_infrastructure_settings() -> None:
    result = await dry_run(
        Namespace(
            source="kicad",
            repository_root=FIXTURES / "kicad",
            revision=REVISION,
            file="Sensor_Temperature.kicad_sym",
            entry="LM35",
            tag=None,
        )
    )
    assert result["status"] == "parsed"
    assert result["draft_status"] == "draft"
    license_snapshot = result["license_snapshot"]
    assert isinstance(license_snapshot, dict)
    assert license_snapshot["spdx"] == "CC-BY-SA-4.0"
