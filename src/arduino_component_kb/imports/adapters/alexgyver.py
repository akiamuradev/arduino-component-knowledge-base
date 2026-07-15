"""Versioned metadata-only adapter for AlexGyver Arduino project pages."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from arduino_component_kb.imports.adapters.base import adapter_drift
from arduino_component_kb.imports.adapters.metadata import collect_metadata
from arduino_component_kb.imports.domain import (
    ParsedComponent,
    ParserDriftError,
    SourcePolicyError,
    normalized_text,
)
from arduino_component_kb.imports.transport import FetchedDocument
from arduino_component_kb.imports.urls import ApprovedUrl, approve_source_url

_PROJECT_PATH = re.compile(r"^/(?P<identifier>[a-z0-9](?:[a-z0-9-]{0,158}[a-z0-9])?)/$")
_INDEX_PATHS = frozenset({"ardu-proj", "articles", "lessons"})


class AlexGyverAdapter:
    source_host = "alexgyver.ru"
    parser_name = "alexgyver_project"
    parser_version = "1.0.0"

    def supports(self, url: str) -> bool:
        try:
            approved = approve_source_url(url)
        except SourcePolicyError:
            return False
        match = _PROJECT_PATH.fullmatch(approved.path_and_query)
        return (
            approved.host == self.source_host
            and match is not None
            and match.group("identifier") not in _INDEX_PATHS
        )

    def parse(self, document: FetchedDocument, *, parsed_at: datetime) -> ParsedComponent:
        requested = self._project_url(document.requested_url, field="requested_url")
        final = self._project_url(document.final_url, field="final_url")
        item_match = _PROJECT_PATH.fullmatch(final.path_and_query)
        if item_match is None or item_match.group("identifier") in _INDEX_PATHS:
            raise adapter_drift(self, "alexgyver_project_path_missing", field="final_url")
        metadata = collect_metadata(document.text(), title_class="entry-title")
        canonical_value = self._single(metadata.canonical_urls, field="canonical_url")
        description = self._single(metadata.descriptions, field="description")
        title_value = self._single(metadata.titles, field="title")
        try:
            canonical = approve_source_url(canonical_value)
        except SourcePolicyError as error:
            raise adapter_drift(
                self, "alexgyver_canonical_invalid", field="canonical_url"
            ) from error
        if canonical.host != self.source_host or canonical.url != final.url:
            raise adapter_drift(self, "alexgyver_canonical_mismatch", field="canonical_url")
        try:
            title = normalized_text(title_value, maximum=160, field_name="title")
            summary = normalized_text(description, maximum=500, field_name="summary")
        except ParserDriftError as error:
            raise adapter_drift(self, "alexgyver_metadata_invalid", field="text") from error
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
            category_hint="motors" if "шаговик" in title.casefold() else None,
            tags=("arduino", "alexgyver"),
        )

    def _project_url(self, value: str, *, field: str) -> ApprovedUrl:
        try:
            approved = approve_source_url(value)
        except SourcePolicyError as error:
            raise adapter_drift(self, "alexgyver_url_invalid", field=field) from error
        if approved.host != self.source_host:
            raise adapter_drift(self, "alexgyver_host_mismatch", field=field)
        return approved

    def _single(self, values: tuple[str, ...], *, field: str) -> str:
        if not values:
            raise adapter_drift(self, "alexgyver_required_metadata_missing", field=field)
        if len(values) != 1:
            raise adapter_drift(self, "alexgyver_metadata_ambiguous", field=field)
        return values[0]
