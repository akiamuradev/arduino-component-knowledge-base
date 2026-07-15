"""Portal-PK versioned fixture, draft contract, and drift diagnostics."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from arduino_component_kb.imports.adapters.base import ComponentSourceAdapter
from arduino_component_kb.imports.adapters.portal_pk import PortalPkAdapter
from arduino_component_kb.imports.domain import ParserDriftError
from arduino_component_kb.imports.transport import FetchedDocument

FIXTURE = Path(__file__).parent / "fixtures" / "portal_pk" / "keypad_4x4_v1.html"
URL = "https://portal-pk.ru/news/325-podklyuchenie-matrichnoi-klaviatury-4h4-arduino.html"
PARSED_AT = datetime(2026, 7, 16, tzinfo=UTC)


def document(body: bytes | None = None) -> FetchedDocument:
    return FetchedDocument(URL, URL, "text/html; charset=utf-8", body or FIXTURE.read_bytes())


def test_portal_pk_adapter_returns_metadata_only_draft() -> None:
    adapter: ComponentSourceAdapter = PortalPkAdapter()
    parsed = adapter.parse(document(), parsed_at=PARSED_AT)

    assert parsed.status == "draft"
    assert parsed.source_policy == "metadata_only"
    assert parsed.source_item_id == "325"
    assert parsed.parser_version == "1.0.0"
    assert parsed.aliases == ("Подключение матричной клавиатуры 4х4 Arduino",)
    assert parsed.category_hint == "input-controls"
    assert parsed.source_content_sha256 == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert "REMOTE" not in parsed.description
    assert not hasattr(parsed, "published_at")


def test_portal_pk_drift_diagnostic_is_typed_and_safe() -> None:
    malformed = FIXTURE.read_text(encoding="utf-8").replace('name="description"', 'name="keywords"')

    with pytest.raises(ParserDriftError) as raised:
        PortalPkAdapter().parse(document(malformed.encode()), parsed_at=PARSED_AT)

    assert raised.value.diagnostic() == {
        "code": "portal_pk_required_metadata_missing",
        "source_host": "portal-pk.ru",
        "parser_name": "portal_pk_component",
        "parser_version": "1.0.0",
        "field": "description",
    }
    assert "REMOTE ARTICLE BODY" not in str(raised.value)


def test_portal_pk_rejects_ambiguous_canonical_metadata() -> None:
    malformed = FIXTURE.read_text(encoding="utf-8").replace(
        "</head>", f'<link rel="canonical" href="{URL}"></head>'
    )

    with pytest.raises(ParserDriftError, match="portal_pk_metadata_ambiguous"):
        PortalPkAdapter().parse(document(malformed.encode()), parsed_at=PARSED_AT)
