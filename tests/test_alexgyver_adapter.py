"""AlexGyver versioned fixture, draft contract, and drift diagnostics."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from arduino_component_kb.imports.adapters.alexgyver import AlexGyverAdapter
from arduino_component_kb.imports.adapters.base import ComponentSourceAdapter
from arduino_component_kb.imports.domain import ParserDriftError
from arduino_component_kb.imports.transport import FetchedDocument

FIXTURE = Path(__file__).parent / "fixtures" / "alexgyver" / "midi_stepper_v1.html"
URL = "https://alexgyver.ru/midi-stepper/"
PARSED_AT = datetime(2026, 7, 16, tzinfo=UTC)


def document(body: bytes | None = None) -> FetchedDocument:
    return FetchedDocument(URL, URL, "text/html; charset=utf-8", body or FIXTURE.read_bytes())


def test_alexgyver_adapter_returns_metadata_only_draft() -> None:
    adapter: ComponentSourceAdapter = AlexGyverAdapter()
    parsed = adapter.parse(document(), parsed_at=PARSED_AT)

    assert parsed.status == "draft"
    assert parsed.source_policy == "metadata_only"
    assert parsed.source_item_id == "midi-stepper"
    assert parsed.parser_version == "1.0.0"
    assert parsed.category_hint == "motors"
    assert parsed.source_content_sha256 == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert "REMOTE" not in parsed.description
    assert not hasattr(parsed, "published_at")


def test_alexgyver_drift_diagnostic_identifies_title_contract() -> None:
    malformed = FIXTURE.read_text(encoding="utf-8").replace("entry-title", "layout-title")

    with pytest.raises(ParserDriftError) as raised:
        AlexGyverAdapter().parse(document(malformed.encode()), parsed_at=PARSED_AT)

    diagnostic = raised.value.diagnostic()
    assert diagnostic["code"] == "alexgyver_required_metadata_missing"
    assert diagnostic["source_host"] == "alexgyver.ru"
    assert diagnostic["parser_version"] == "1.0.0"
    assert diagnostic["field"] == "title"


def test_alexgyver_listing_is_not_treated_as_component_project() -> None:
    assert not AlexGyverAdapter().supports("https://alexgyver.ru/ardu-proj/")


def test_alexgyver_rejects_canonical_mismatch() -> None:
    malformed = FIXTURE.read_text(encoding="utf-8").replace(
        "https://alexgyver.ru/midi-stepper/", "https://alexgyver.ru/other-project/"
    )

    with pytest.raises(ParserDriftError, match="alexgyver_canonical_mismatch"):
        AlexGyverAdapter().parse(document(malformed.encode()), parsed_at=PARSED_AT)
