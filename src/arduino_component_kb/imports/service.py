"""Orchestrate safe fetching and exactly one source-specific adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from arduino_component_kb.imports.adapters.base import ComponentSourceAdapter
from arduino_component_kb.imports.domain import ParsedComponent, SourcePolicyError
from arduino_component_kb.imports.transport import FetchedDocument
from arduino_component_kb.imports.urls import approve_source_url


class DocumentFetcher(Protocol):
    async def fetch(self, url: str) -> FetchedDocument: ...


class ComponentParser:
    """Select one explicit adapter; never fall back to a generic scraper."""

    def __init__(
        self,
        fetcher: DocumentFetcher,
        adapters: tuple[ComponentSourceAdapter, ...],
    ) -> None:
        self.fetcher = fetcher
        self.adapters = adapters

    async def parse(self, url: str, *, parsed_at: datetime | None = None) -> ParsedComponent:
        approved = approve_source_url(url)
        matches = tuple(adapter for adapter in self.adapters if adapter.supports(approved.url))
        if len(matches) != 1:
            raise SourcePolicyError("source_adapter_not_implemented")
        document = await self.fetcher.fetch(approved.url)
        return matches[0].parse(document, parsed_at=parsed_at or datetime.now(UTC))
