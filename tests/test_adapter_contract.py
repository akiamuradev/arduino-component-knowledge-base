"""Common contract tests for every registered source adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from arduino_component_kb.imports.adapters import DEFAULT_ADAPTERS
from arduino_component_kb.imports.domain import ParsedComponent
from arduino_component_kb.imports.transport import FetchedDocument

ROOT = Path(__file__).parent
CASES = (
    (
        "https://arduino-tex.ru/news/229/modul-dzhoistika-ky-023-dual-axis-joystick-podklyuchenie-k-arduino.html",
        ROOT / "fixtures" / "arduino_tex" / "ky_023.html",
    ),
    (
        "https://portal-pk.ru/news/325-podklyuchenie-matrichnoi-klaviatury-4h4-arduino.html",
        ROOT / "fixtures" / "portal_pk" / "keypad_4x4_v1.html",
    ),
    (
        "https://alexgyver.ru/midi-stepper/",
        ROOT / "fixtures" / "alexgyver" / "midi_stepper_v1.html",
    ),
)


def test_default_adapters_have_unique_identity_and_semantic_versions() -> None:
    identities = {(adapter.source_host, adapter.parser_name) for adapter in DEFAULT_ADAPTERS}
    assert len(DEFAULT_ADAPTERS) == 3
    assert len(identities) == len(DEFAULT_ADAPTERS)
    assert all(adapter.parser_version == "1.0.0" for adapter in DEFAULT_ADAPTERS)


@pytest.mark.parametrize(("url", "fixture"), CASES)
def test_every_adapter_implements_the_same_draft_contract(url: str, fixture: Path) -> None:
    matches = tuple(adapter for adapter in DEFAULT_ADAPTERS if adapter.supports(url))
    assert len(matches) == 1
    document = FetchedDocument(url, url, "text/html; charset=utf-8", fixture.read_bytes())

    parsed = matches[0].parse(document, parsed_at=datetime(2026, 7, 16, tzinfo=UTC))

    assert isinstance(parsed, ParsedComponent)
    assert parsed.status == "draft"
    assert parsed.source_policy == "metadata_only"
    assert parsed.source_host == matches[0].source_host
    assert parsed.parser_name == matches[0].parser_name
    assert parsed.parser_version == matches[0].parser_version
