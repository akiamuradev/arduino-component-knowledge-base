"""Versioned metadata-only adapter for portal-pk.ru component lessons."""

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

_ARTICLE_PATH = re.compile(
    r"^/news/(?P<identifier>[1-9][0-9]*)-(?P<slug>[a-z0-9][a-z0-9-]*)\.html$"
)
_LESSON_PREFIX = re.compile(r"^#[0-9]+\.\s*")


class PortalPkAdapter:
    source_host = "portal-pk.ru"
    parser_name = "portal_pk_component"
    parser_version = "1.0.0"

    def supports(self, url: str) -> bool:
        try:
            approved = approve_source_url(url)
        except SourcePolicyError:
            return False
        return (
            approved.host == self.source_host
            and _ARTICLE_PATH.fullmatch(approved.path_and_query) is not None
        )

    def parse(self, document: FetchedDocument, *, parsed_at: datetime) -> ParsedComponent:
        requested = self._article_url(document.requested_url, field="requested_url")
        final = self._article_url(document.final_url, field="final_url")
        item_match = _ARTICLE_PATH.fullmatch(final.path_and_query)
        if item_match is None:
            raise adapter_drift(self, "portal_pk_article_path_missing", field="final_url")
        metadata = collect_metadata(document.text(), title_class="heading1")
        canonical_value = self._single(metadata.canonical_urls, field="canonical_url")
        description = self._single(metadata.descriptions, field="description")
        title_value = self._single(metadata.titles, field="title")
        try:
            canonical = approve_source_url(canonical_value)
        except SourcePolicyError as error:
            raise adapter_drift(
                self, "portal_pk_canonical_invalid", field="canonical_url"
            ) from error
        if canonical.host != self.source_host or canonical.url != final.url:
            raise adapter_drift(self, "portal_pk_canonical_mismatch", field="canonical_url")
        try:
            title = normalized_text(title_value, maximum=160, field_name="title")
            summary = normalized_text(description, maximum=500, field_name="summary")
        except ParserDriftError as error:
            raise adapter_drift(self, "portal_pk_metadata_invalid", field="text") from error
        alias = _LESSON_PREFIX.sub("", title)
        aliases = (alias,) if alias != title else ()
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
            category_hint="input-controls" if "клавиатур" in title.casefold() else None,
            tags=("arduino", "portal-pk"),
        )

    def _article_url(self, value: str, *, field: str) -> ApprovedUrl:
        try:
            approved = approve_source_url(value)
        except SourcePolicyError as error:
            raise adapter_drift(self, "portal_pk_url_invalid", field=field) from error
        if approved.host != self.source_host:
            raise adapter_drift(self, "portal_pk_host_mismatch", field=field)
        return approved

    def _single(self, values: tuple[str, ...], *, field: str) -> str:
        if not values:
            raise adapter_drift(self, "portal_pk_required_metadata_missing", field=field)
        if len(values) != 1:
            raise adapter_drift(self, "portal_pk_metadata_ambiguous", field=field)
        return values[0]
