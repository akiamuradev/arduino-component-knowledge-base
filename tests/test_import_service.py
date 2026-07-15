"""First-source orchestration tests without network or persistence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from arduino_component_kb.imports.adapters.arduino_tex import ArduinoTexAdapter
from arduino_component_kb.imports.domain import SourcePolicyError
from arduino_component_kb.imports.service import ComponentParser
from arduino_component_kb.imports.transport import FetchedDocument

URL = (
    "https://arduino-tex.ru/news/229/"
    "modul-dzhoistika-ky-023-dual-axis-joystick-podklyuchenie-k-arduino.html"
)


class RecordingFetcher:
    def __init__(self, document: FetchedDocument) -> None:
        self.document = document
        self.urls: list[str] = []

    async def fetch(self, url: str) -> FetchedDocument:
        self.urls.append(url)
        return self.document


async def test_component_parser_fetches_and_returns_only_draft(fixture_html: bytes) -> None:
    document = FetchedDocument(URL, URL, "text/html; charset=utf-8", fixture_html)
    fetcher = RecordingFetcher(document)
    parser = ComponentParser(fetcher, (ArduinoTexAdapter(),))

    parsed = await parser.parse(URL, parsed_at=datetime(2026, 7, 16, tzinfo=UTC))

    assert parsed.status == "draft"
    assert parsed.source_item_id == "229"
    assert fetcher.urls == [URL]


async def test_allowed_host_without_adapter_is_not_fetched(fixture_html: bytes) -> None:
    document = FetchedDocument(URL, URL, "text/html", fixture_html)
    fetcher = RecordingFetcher(document)
    parser = ComponentParser(fetcher, (ArduinoTexAdapter(),))

    with pytest.raises(SourcePolicyError, match="source_adapter_not_implemented"):
        await parser.parse("https://portal-pk.ru/component/example")
    assert fetcher.urls == []
