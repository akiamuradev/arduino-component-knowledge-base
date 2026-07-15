"""Versioned metadata-only adapter for arduino-tex.ru component articles."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from html.parser import HTMLParser

from arduino_component_kb.imports.adapters.base import adapter_drift
from arduino_component_kb.imports.domain import (
    ParsedComponent,
    ParserDriftError,
    SourcePolicyError,
    normalized_text,
)
from arduino_component_kb.imports.transport import FetchedDocument
from arduino_component_kb.imports.urls import approve_source_url

_ITEM_PATH = re.compile(r"^/news/(?P<identifier>[1-9][0-9]*)/")
_MODEL = re.compile(r"\bKY-[0-9]{3}\b", re.IGNORECASE)
_PARENTHETICAL = re.compile(r"\(([^()]{2,80})\)")


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical: str | None = None
        self.description: str | None = None
        self.title_parts: list[str] = []
        self._title_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = frozenset((attributes.get("class") or "").split())
        if tag == "link" and (attributes.get("rel") or "").lower() == "canonical":
            self.canonical = attributes.get("href")
        elif tag == "meta" and (attributes.get("name") or "").lower() == "description":
            self.description = attributes.get("content")
        if tag == "h1" and "heading1" in classes:
            self._title_depth = 1
        elif self._title_depth:
            self._title_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._title_depth:
            self._title_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self.title_parts.append(data)


class ArduinoTexAdapter:
    source_host = "arduino-tex.ru"
    parser_name = "arduino_tex_component"
    parser_version = "1.0.0"

    def supports(self, url: str) -> bool:
        try:
            approved = approve_source_url(url)
        except SourcePolicyError:
            return False
        return (
            approved.host == self.source_host
            and _ITEM_PATH.match(approved.path_and_query) is not None
        )

    def parse(self, document: FetchedDocument, *, parsed_at: datetime) -> ParsedComponent:
        requested = approve_source_url(document.requested_url)
        if requested.host != self.source_host:
            raise adapter_drift(self, "arduino_tex_requested_host_mismatch", field="requested_url")
        final = approve_source_url(document.final_url)
        if final.host != self.source_host:
            raise adapter_drift(self, "arduino_tex_final_host_mismatch", field="final_url")
        item_match = _ITEM_PATH.match(final.path_and_query)
        if item_match is None:
            raise adapter_drift(self, "arduino_tex_article_path_missing", field="final_url")
        parser = _MetadataParser()
        parser.feed(document.text())
        if parser.canonical is None or parser.description is None or not parser.title_parts:
            raise adapter_drift(self, "arduino_tex_required_metadata_missing", field="metadata")
        canonical = approve_source_url(parser.canonical)
        if canonical.host != self.source_host or canonical.url != final.url:
            raise adapter_drift(self, "arduino_tex_canonical_mismatch", field="canonical_url")
        try:
            title = normalized_text(" ".join(parser.title_parts), maximum=160, field_name="title")
            summary = normalized_text(parser.description, maximum=500, field_name="summary")
        except ParserDriftError as error:
            raise adapter_drift(self, "arduino_tex_metadata_invalid", field="text") from error
        model_match = _MODEL.search(title)
        model = model_match.group(0).upper() if model_match else None
        aliases = tuple(
            dict.fromkeys(
                value
                for value in (
                    model,
                    *(
                        normalized_text(match, maximum=80, field_name="alias")
                        for match in _PARENTHETICAL.findall(title)
                    ),
                )
                if value is not None
            )
        )
        tags = tuple(value for value in ("arduino", "module", model) if value is not None)
        return ParsedComponent(
            source_host=self.source_host,
            source_url=requested.url,
            canonical_url=canonical.url,
            source_item_id=item_match.group("identifier"),
            source_content_sha256=hashlib.sha256(document.body).hexdigest(),
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            parsed_at=parsed_at,
            title=title,
            summary=summary,
            description=summary,
            aliases=aliases,
            model=model,
            category_hint="input-controls",
            tags=tags,
        )
