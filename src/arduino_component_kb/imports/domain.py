"""Validated parser output that can only represent a draft component."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

_SPACE = re.compile(r"\s+")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ParserError(Exception):
    """Base class for safe typed import failures."""


class ParserDriftError(ParserError):
    """Safe structured diagnostic for a versioned adapter contract mismatch."""

    def __init__(
        self,
        code: str,
        *,
        source_host: str | None = None,
        parser_name: str | None = None,
        parser_version: str | None = None,
        field: str | None = None,
    ) -> None:
        self.code = code
        self.source_host = source_host
        self.parser_name = parser_name
        self.parser_version = parser_version
        self.field = field
        context = ", ".join(
            f"{name}={value}"
            for name, value in (
                ("source", source_host),
                ("parser", parser_name),
                ("version", parser_version),
                ("field", field),
            )
            if value is not None
        )
        super().__init__(f"{code}: {context}" if context else code)

    def diagnostic(self) -> dict[str, str]:
        """Return bounded operator context without remote HTML or exception details."""
        return {
            key: value
            for key, value in (
                ("code", self.code),
                ("source_host", self.source_host),
                ("parser_name", self.parser_name),
                ("parser_version", self.parser_version),
                ("field", self.field),
            )
            if value is not None
        }


class SourcePolicyError(ParserError):
    """The requested URL or response violates the source security policy."""


class SourceFetchError(ParserError):
    """The approved source could not be fetched safely."""


class RetryableImportError(Exception):
    """A transient import failure with a bounded retry delay."""

    def __init__(self, delay_ms: int) -> None:
        self.delay_ms = delay_ms
        super().__init__("import_retry_required")


def normalized_text(value: str, *, maximum: int, field_name: str) -> str:
    """Normalize remote text and reject blank or oversized values."""
    normalized = _SPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()
    if not normalized or len(normalized) > maximum:
        raise ParserDriftError(f"{field_name} is blank or exceeds its limit")
    return normalized


@dataclass(frozen=True, slots=True)
class ParsedComponent:
    """Metadata-only parser result; publication is intentionally unrepresentable."""

    source_host: str
    source_url: str
    canonical_url: str
    source_item_id: str
    source_content_sha256: str
    parser_name: str
    parser_version: str
    parsed_at: datetime
    title: str
    summary: str
    description: str
    aliases: tuple[str, ...] = ()
    manufacturer: str | None = None
    model: str | None = None
    purpose: str | None = None
    usage_notes: str | None = None
    safety_notes: str | None = None
    category_hint: str | None = None
    tags: tuple[str, ...] = ()
    status: Literal["draft"] = field(default="draft", init=False)
    source_policy: Literal["metadata_only"] = field(default="metadata_only", init=False)

    def __post_init__(self) -> None:
        if self.parsed_at.tzinfo is None or self.parsed_at.utcoffset() is None:
            raise ValueError("parsed_at must be timezone-aware")
        limits = {
            "title": (self.title, 160),
            "summary": (self.summary, 500),
            "description": (self.description, 2_000),
            "source_item_id": (self.source_item_id, 160),
            "parser_name": (self.parser_name, 80),
            "parser_version": (self.parser_version, 40),
        }
        for name, (value, maximum) in limits.items():
            if not value or len(value) > maximum:
                raise ValueError(f"{name} is blank or exceeds its limit")
        if len(self.aliases) > 20 or len(self.tags) > 20:
            raise ValueError("parsed collections exceed their limits")
        if any(not value or len(value) > 160 for value in (*self.aliases, *self.tags)):
            raise ValueError("parsed collection item is blank or oversized")
        if _SHA256.fullmatch(self.source_content_sha256) is None:
            raise ValueError("source_content_sha256 must be a lowercase SHA-256 digest")
