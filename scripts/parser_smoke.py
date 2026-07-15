"""Dependency-isolated smoke test for pinned fetching and all pilot adapters."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx2

from arduino_component_kb.imports.adapters import DEFAULT_ADAPTERS
from arduino_component_kb.imports.service import ComponentParser
from arduino_component_kb.imports.transport import SafeHttpFetcher

CASES = (
    (
        "https://arduino-tex.ru/news/229/"
        "modul-dzhoistika-ky-023-dual-axis-joystick-podklyuchenie-k-arduino.html",
        "arduino-tex.ru",
        "arduino_tex/ky_023.html",
        "229",
    ),
    (
        "https://portal-pk.ru/news/325-podklyuchenie-matrichnoi-klaviatury-4h4-arduino.html",
        "portal-pk.ru",
        "portal_pk/keypad_4x4_v1.html",
        "325",
    ),
    (
        "https://alexgyver.ru/midi-stepper/",
        "alexgyver.ru",
        "alexgyver/midi_stepper_v1.html",
        "midi-stepper",
    ),
)
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
FIXTURE_BY_HOST = {host: FIXTURES / fixture for _, host, fixture, _ in CASES}


class SmokeResolver:
    async def resolve(self, host: str) -> tuple[str, ...]:
        assert host in FIXTURE_BY_HOST
        return ("93.184.216.34",)


def fixture_response(request: httpx2.Request) -> httpx2.Response:
    assert request.url.host == "93.184.216.34"
    source_host = request.headers["host"]
    assert request.extensions["sni_hostname"] == source_host
    return httpx2.Response(
        200,
        headers={"Content-Type": "text/html; charset=utf-8"},
        content=FIXTURE_BY_HOST[source_host].read_bytes(),
    )


async def smoke() -> None:
    parser = ComponentParser(
        SafeHttpFetcher(
            resolver=SmokeResolver(),
            transport=httpx2.MockTransport(fixture_response),
        ),
        DEFAULT_ADAPTERS,
    )
    for url, source_host, _, source_item_id in CASES:
        parsed = await parser.parse(url, parsed_at=datetime.now(UTC))
        assert parsed.status == "draft"
        assert parsed.source_policy == "metadata_only"
        assert parsed.source_host == source_host
        assert parsed.source_item_id == source_item_id


def main() -> int:
    asyncio.run(smoke())
    print("Safe three-source parser smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
