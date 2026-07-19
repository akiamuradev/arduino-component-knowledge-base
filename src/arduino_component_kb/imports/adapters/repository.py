"""Contract implemented only by registered immutable repository adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from arduino_component_kb.imports.repository_domain import (
    ParsedRepositoryComponent,
    RepositoryEntry,
    RepositorySnapshot,
)


class RepositorySourceAdapter(Protocol):
    source_key: str
    repository_url: str
    parser_name: str
    parser_version: str

    async def validate_revision(self, revision: str) -> str: ...

    async def discover(
        self, snapshot: RepositorySnapshot, *, query: str | None = None, limit: int = 100
    ) -> tuple[RepositoryEntry, ...]: ...

    async def parse_entry(
        self,
        snapshot: RepositorySnapshot,
        entry: RepositoryEntry,
        *,
        parsed_at: datetime,
        source_tag: str | None = None,
    ) -> ParsedRepositoryComponent: ...
