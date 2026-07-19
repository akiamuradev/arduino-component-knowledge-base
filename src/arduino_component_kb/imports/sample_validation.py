"""Bounded live-source smoke check for the approved repository samples."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from arduino_component_kb.imports.acquisition import RepositoryAcquirer
from arduino_component_kb.imports.adapters.kicad_symbols import KicadSymbolsAdapter
from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.repository_domain import ParseStatus, RepositoryEntry

SEEED_REQUESTED_REVISION = "docusaurus-version"
SEEED_SAMPLE_PATHS = (
    "sites/en/docs/Sensor/Grove/Grove_Accessories/Switch&Button/Grove-Button.md",
    "sites/en/docs/Sensor/Grove/Grove_Accessories/Actuator/Grove-Relay.md",
    "sites/en/docs/Sensor/Grove/Grove_Sensors/Temperature/Grove-Temperature_Sensor.md",
    "sites/en/docs/Sensor/Grove/Grove_Sensors/Proximity/Grove-Ultrasonic_Ranger.md",
    "sites/en/docs/Sensor/Grove/Grove_Sensors/Light/Grove-Light_Sensor.md",
)
KICAD_REQUESTED_REVISION = "9.0.9.1"
KICAD_SAMPLE_PATH = "Sensor_Temperature.kicad_sym"
KICAD_SAMPLE_ENTRIES = (
    "AD8494",
    "BD1020HFV",
    "DS1621",
    "DS1804",
    "DS1822Z",
    "DS18B20U",
    "DS28EA00",
    "KTY81",
    "KTY82",
    "KTY83",
)
_ACCEPTED = frozenset({ParseStatus.PARSED, ParseStatus.PARSED_WITH_WARNINGS})


async def validate_samples() -> dict[str, object]:
    """Fetch and parse exactly five Seeed documents and ten KiCad symbols."""
    acquirer = RepositoryAcquirer()
    now = datetime.now(UTC)
    seeed_adapter = SeeedWikiAdapter()
    seeed_results: list[dict[str, object]] = []
    seeed_revision = SEEED_REQUESTED_REVISION
    for path in SEEED_SAMPLE_PATHS:
        acquired = await acquirer.acquire(
            seeed_adapter.source_key,
            seeed_adapter.repository_url,
            seeed_revision,
            path,
        )
        seeed_revision = acquired.snapshot.revision
        parsed = await seeed_adapter.parse_entry(
            acquired.snapshot,
            RepositoryEntry(path),
            parsed_at=now,
            source_tag=SEEED_REQUESTED_REVISION,
        )
        seeed_results.append(
            {
                "file_path": path,
                "status": parsed.status.value,
                "title": parsed.normalized_fields.get("title"),
                "warnings": list(parsed.warnings),
            }
        )

    kicad_adapter = KicadSymbolsAdapter()
    acquired_kicad = await acquirer.acquire(
        kicad_adapter.source_key,
        kicad_adapter.repository_url,
        KICAD_REQUESTED_REVISION,
        KICAD_SAMPLE_PATH,
    )
    kicad_results: list[dict[str, object]] = []
    for entry_name in KICAD_SAMPLE_ENTRIES:
        parsed = await kicad_adapter.parse_entry(
            acquired_kicad.snapshot,
            RepositoryEntry(KICAD_SAMPLE_PATH, entry_name=entry_name),
            parsed_at=now,
            source_tag=KICAD_REQUESTED_REVISION,
        )
        kicad_results.append(
            {
                "file_path": KICAD_SAMPLE_PATH,
                "entry_name": entry_name,
                "status": parsed.status.value,
                "warnings": list(parsed.warnings),
            }
        )

    failures = [
        item
        for item in (*seeed_results, *kicad_results)
        if ParseStatus(str(item["status"])) not in _ACCEPTED
    ]
    return {
        "ok": not failures,
        "seeed_revision": seeed_revision,
        "kicad_revision": acquired_kicad.snapshot.revision,
        "seeed": seeed_results,
        "kicad": kicad_results,
        "failure_count": len(failures),
    }


def main() -> None:
    result = asyncio.run(validate_samples())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
