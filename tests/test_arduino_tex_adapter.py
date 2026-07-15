"""Versioned arduino-tex.ru fixture and draft-only parser tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from arduino_component_kb.imports.adapters.arduino_tex import ArduinoTexAdapter
from arduino_component_kb.imports.adapters.base import ComponentSourceAdapter
from arduino_component_kb.imports.domain import ParserDriftError, SourcePolicyError
from arduino_component_kb.imports.transport import FetchedDocument

FIXTURE = Path(__file__).parent / "fixtures" / "arduino_tex" / "ky_023.html"
URL = (
    "https://arduino-tex.ru/news/229/"
    "modul-dzhoistika-ky-023-dual-axis-joystick-podklyuchenie-k-arduino.html"
)


def fixture_document(body: bytes | None = None) -> FetchedDocument:
    return FetchedDocument(URL, URL, "text/html; charset=utf-8", body or FIXTURE.read_bytes())


def test_adapter_protocol_parses_metadata_only_draft() -> None:
    adapter: ComponentSourceAdapter = ArduinoTexAdapter()
    parsed = adapter.parse(fixture_document(), parsed_at=datetime(2026, 7, 16, tzinfo=UTC))

    assert parsed.status == "draft"
    assert parsed.source_policy == "metadata_only"
    assert parsed.source_item_id == "229"
    assert parsed.source_content_sha256 == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert parsed.model == "KY-023"
    assert parsed.aliases == ("KY-023", "Dual Axis Joystick")
    assert parsed.category_hint == "input-controls"
    assert "remote scripts" not in parsed.description
    assert "/uploads/untrusted.jpg" not in parsed.description
    assert not hasattr(parsed, "published_at")


def test_adapter_reports_parser_drift_instead_of_partial_result() -> None:
    malformed = b"<html><h1>Layout changed</h1></html>"
    with pytest.raises(ParserDriftError, match="required_metadata_missing"):
        ArduinoTexAdapter().parse(
            fixture_document(malformed),
            parsed_at=datetime(2026, 7, 16, tzinfo=UTC),
        )


def test_adapter_rejects_naive_parser_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ArduinoTexAdapter().parse(fixture_document(), parsed_at=datetime(2026, 7, 16))


def test_adapter_rejects_untrusted_requested_host() -> None:
    document = FetchedDocument(
        "https://evil.example/news/229/article.html",
        URL,
        "text/html; charset=utf-8",
        FIXTURE.read_bytes(),
    )

    with pytest.raises(SourcePolicyError, match="source_host_not_allowed"):
        ArduinoTexAdapter().parse(document, parsed_at=datetime(2026, 7, 16, tzinfo=UTC))
