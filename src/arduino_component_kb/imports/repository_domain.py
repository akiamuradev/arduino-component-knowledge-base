"""Typed, immutable contracts for registered repository imports."""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class SourceType(StrEnum):
    WEBSITE = "website"
    GIT_REPOSITORY = "git_repository"
    OFFICIAL_LIBRARY = "official_library"


class SourceStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISABLED = "disabled"


class PermissionStatus(StrEnum):
    UNKNOWN = "unknown"
    DENIED = "denied"
    LICENSE_GRANTED = "license_granted"


class ParseStatus(StrEnum):
    PARSED = "parsed"
    PARSED_WITH_WARNINGS = "parsed_with_warnings"
    UNSUPPORTED_DOCUMENT = "unsupported_document"
    SOURCE_DRIFT = "source_drift"
    INVALID_METADATA = "invalid_metadata"
    LICENSE_MISSING = "license_missing"
    FAILED = "failed"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def require_commit_sha(value: str) -> str:
    normalized = value.strip().casefold()
    if _COMMIT_SHA.fullmatch(normalized) is None:
        raise ValueError("source_revision_must_be_full_commit_sha")
    return normalized


def normalize_repository_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if not normalized.startswith("https://"):
        raise ValueError("repository_url_must_use_https")
    return normalized


def normalize_repository_path(value: str) -> str:
    if not value or "\\" in value or value.startswith("/"):
        raise ValueError("repository_path_invalid")
    normalized = posixpath.normpath(value)
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise ValueError("repository_path_outside_snapshot")
    return normalized


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    repository_url: str
    revision: str
    files: Mapping[str, bytes]

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_url", normalize_repository_url(self.repository_url))
        object.__setattr__(self, "revision", require_commit_sha(self.revision))
        normalized: dict[str, bytes] = {}
        for path, content in self.files.items():
            safe_path = normalize_repository_path(path)
            if len(content) > 2 * 1024 * 1024:
                raise ValueError("repository_file_too_large")
            normalized[safe_path] = content
        if len(normalized) > 10_000:
            raise ValueError("repository_file_count_exceeded")
        object.__setattr__(self, "files", normalized)

    def read(self, path: str) -> bytes:
        try:
            return self.files[normalize_repository_path(path)]
        except KeyError as error:
            raise ValueError("repository_file_not_found") from error


@dataclass(frozen=True, slots=True)
class RepositoryEntry:
    file_path: str
    entry_name: str | None = None
    title: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_path", normalize_repository_path(self.file_path))
        if self.entry_name is not None and not self.entry_name.strip():
            raise ValueError("repository_entry_name_blank")


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    repository_url: str
    source_revision: str
    source_file_path: str
    section_or_property: str
    confidence: Confidence
    transformation: str

    def as_dict(self) -> dict[str, str]:
        return {
            "repository_url": self.repository_url,
            "source_revision": self.source_revision,
            "source_file_path": self.source_file_path,
            "section_or_property": self.section_or_property,
            "confidence": self.confidence.value,
            "transformation": self.transformation,
        }


@dataclass(frozen=True, slots=True)
class LicenseSnapshot:
    name: str
    spdx: str
    url: str
    attribution: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.name, self.spdx, self.url, self.attribution)):
            raise ValueError("license_snapshot_incomplete")


@dataclass(frozen=True, slots=True)
class ParsedRepositoryComponent:
    source_key: str
    repository_url: str
    source_revision: str
    source_tag: str | None
    source_file_path: str
    source_entry_name: str | None
    original_url: str
    parser_name: str
    parser_version: str
    parsed_at: datetime
    status: ParseStatus
    normalized_fields: Mapping[str, object]
    provenance: Mapping[str, tuple[FieldProvenance, ...]]
    license_snapshot: LicenseSnapshot
    modifications_notice: str
    warnings: tuple[str, ...] = ()
    draft_status: str = field(default="draft", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_url", normalize_repository_url(self.repository_url))
        object.__setattr__(self, "source_revision", require_commit_sha(self.source_revision))
        object.__setattr__(
            self, "source_file_path", normalize_repository_path(self.source_file_path)
        )
        if self.parsed_at.tzinfo is None or self.parsed_at.utcoffset() is None:
            raise ValueError("parsed_at_must_be_timezone_aware")
        if self.status in {ParseStatus.PARSED, ParseStatus.PARSED_WITH_WARNINGS}:
            missing = set(self.normalized_fields).difference(self.provenance)
            empty = {key for key, values in self.provenance.items() if not values}
            if missing or empty:
                raise ValueError("parsed_field_provenance_missing")
        if self.status is ParseStatus.PARSED and self.warnings:
            raise ValueError("parsed_status_cannot_contain_warnings")
        if self.status is ParseStatus.PARSED_WITH_WARNINGS and not self.warnings:
            raise ValueError("warning_status_requires_warning")

    @property
    def idempotency_key(self) -> str:
        identity = json.dumps(
            [
                self.source_key,
                self.repository_url,
                self.source_revision,
                self.source_file_path,
                self.source_entry_name or "",
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return f"repo-v1:{sha256(identity.encode()).hexdigest()}"

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source_key,
            "repository": self.repository_url,
            "revision": self.source_revision,
            "tag": self.source_tag,
            "file": self.source_file_path,
            "entry_name": self.source_entry_name,
            "original_url": self.original_url,
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "status": self.status.value,
            "warnings": list(self.warnings),
            "normalized_fields": dict(self.normalized_fields),
            "provenance": {
                key: [item.as_dict() for item in values] for key, values in self.provenance.items()
            },
            "license_snapshot": {
                "name": self.license_snapshot.name,
                "spdx": self.license_snapshot.spdx,
                "url": self.license_snapshot.url,
                "attribution": self.license_snapshot.attribution,
            },
            "modifications_notice": self.modifications_notice,
            "idempotency_key": self.idempotency_key,
            "draft_status": self.draft_status,
        }
