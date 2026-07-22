"""Golden baseline for repository parsers before the import pipeline refactor."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from arduino_component_kb.imports.adapters.kicad_symbols import KicadSymbolsAdapter
from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.repository_domain import (
    ParsedRepositoryComponent,
    RepositoryEntry,
    RepositorySnapshot,
)

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden" / "imports" / "repository_parsers_v1.json"
REVISION = "a" * 40
PARSED_AT = datetime(2026, 7, 16, tzinfo=UTC)

SEEED_CASES = (
    "alternative_headings.mdx",
    "broken_frontmatter.mdx",
    "communication_module.md",
    "complete.md",
    "development_board.md",
    "power_module.md",
    "unknown_structure.md",
    "without_specifications.md",
)
KICAD_CASES = (
    ("Audio_Outside.kicad_sym", "AudioOnly"),
    ("Display_Graphic.kicad_sym", "SSD1306"),
    ("MCU_Test.kicad_sym", "ATmega328P"),
    ("Relay_Missing_Datasheet.kicad_sym", "Relay_SPDT"),
    ("Sensor_Broken.kicad_sym", "Broken"),
    ("Sensor_Temperature.kicad_sym", "LM35"),
    ("Sensor_Unknown_Electrical.kicad_sym", "FutureSensor"),
    ("Switch_Filters.kicad_sym", "SW_Push"),
)


def _snapshot(source: str, file_name: str) -> RepositorySnapshot:
    adapter = SeeedWikiAdapter() if source == "seeed" else KicadSymbolsAdapter()
    return RepositorySnapshot(
        adapter.repository_url,
        REVISION,
        {file_name: (FIXTURES / source / file_name).read_bytes()},
    )


def _golden_projection(parsed: ParsedRepositoryComponent) -> dict[str, object]:
    assert set(parsed.normalized_fields) == set(parsed.provenance)
    return {
        "normalized_fields": dict(parsed.normalized_fields),
        "status": parsed.status.value,
        "warnings": list(parsed.warnings),
    }


async def test_repository_parsers_match_pre_refactor_golden_baseline() -> None:
    expected = cast(
        dict[str, dict[str, dict[str, object]]],
        json.loads(GOLDEN.read_text(encoding="utf-8")),
    )
    actual: dict[str, dict[str, dict[str, object]]] = {"seeed": {}, "kicad": {}}

    seeed = SeeedWikiAdapter()
    for file_name in SEEED_CASES:
        parsed = await seeed.parse_entry(
            _snapshot("seeed", file_name),
            RepositoryEntry(file_name),
            parsed_at=PARSED_AT,
        )
        actual["seeed"][file_name] = _golden_projection(parsed)

    kicad = KicadSymbolsAdapter()
    for file_name, symbol_name in KICAD_CASES:
        parsed = await kicad.parse_entry(
            _snapshot("kicad", file_name),
            RepositoryEntry(file_name, entry_name=symbol_name),
            parsed_at=PARSED_AT,
        )
        actual["kicad"][f"{file_name}#{symbol_name}"] = _golden_projection(parsed)

    assert len(actual["seeed"]) >= 8
    assert len(actual["kicad"]) >= 8
    assert actual == expected
