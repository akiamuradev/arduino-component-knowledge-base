"""Source adapter protocol shared by parser orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from arduino_component_kb.imports.domain import ParsedComponent, ParserDriftError
from arduino_component_kb.imports.transport import FetchedDocument


class ComponentSourceAdapter(Protocol):
    source_host: str
    parser_name: str
    parser_version: str

    def supports(self, url: str) -> bool: ...

    def parse(self, document: FetchedDocument, *, parsed_at: datetime) -> ParsedComponent: ...


def adapter_drift(
    adapter: ComponentSourceAdapter, code: str, *, field: str | None = None
) -> ParserDriftError:
    """Create one safe diagnostic shape for every source adapter."""
    return ParserDriftError(
        code,
        source_host=adapter.source_host,
        parser_name=adapter.parser_name,
        parser_version=adapter.parser_version,
        field=field,
    )
