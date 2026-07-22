"""Source artifact, evidence and warning models for extracted facts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

_SOURCE_KEY = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_METHOD = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,39}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,63}/[a-z0-9][a-z0-9.+-]{0,63}$")
_WARNING_CODE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


def _required_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise ValueError(f"{key}_must_be_string")
    return item


def _optional_string(value: Mapping[str, object], key: str) -> str | None:
    item = value.get(key)
    if item is not None and not isinstance(item, str):
        raise ValueError(f"{key}_must_be_string_or_null")
    return item


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(code)
    return value


def _object_list(value: Mapping[str, object], key: str) -> list[object]:
    items = value.get(key, [])
    if not isinstance(items, list):
        raise ValueError(f"{key}_must_be_array")
    return list(items)


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name}_must_be_timezone_aware")


@dataclass(frozen=True, slots=True)
class SourceReference:
    source_key: str
    source_url: str | None = None
    source_path: str | None = None
    source_revision: str | None = None

    def __post_init__(self) -> None:
        if _SOURCE_KEY.fullmatch(self.source_key) is None:
            raise ValueError("source_reference_key_invalid")
        if self.source_url is None and self.source_path is None:
            raise ValueError("source_reference_locator_missing")
        if self.source_url is not None:
            parsed = urlsplit(self.source_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or len(self.source_url) > 2_000
            ):
                raise ValueError("source_reference_url_invalid")
        if self.source_path is not None and (
            not self.source_path.strip()
            or "\x00" in self.source_path
            or len(self.source_path) > 1_000
        ):
            raise ValueError("source_reference_path_invalid")
        if self.source_revision is not None and (
            not self.source_revision.strip() or len(self.source_revision) > 160
        ):
            raise ValueError("source_reference_revision_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "source_key": self.source_key,
            "source_url": self.source_url,
            "source_path": self.source_path,
            "source_revision": self.source_revision,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> SourceReference:
        return cls(
            source_key=_required_string(value, "source_key"),
            source_url=_optional_string(value, "source_url"),
            source_path=_optional_string(value, "source_path"),
            source_revision=_optional_string(value, "source_revision"),
        )


@dataclass(frozen=True, slots=True)
class EvidenceFragment:
    source: SourceReference
    raw_text: str
    extraction_method: str
    parser_version: str
    selector: str | None = None
    section: str | None = None

    def __post_init__(self) -> None:
        if not self.raw_text.strip() or len(self.raw_text) > 100_000:
            raise ValueError("evidence_raw_text_invalid")
        if _METHOD.fullmatch(self.extraction_method) is None:
            raise ValueError("evidence_extraction_method_invalid")
        if _VERSION.fullmatch(self.parser_version) is None:
            raise ValueError("evidence_parser_version_invalid")
        if self.selector is None and self.section is None:
            raise ValueError("evidence_location_missing")
        for field_name, value in (("selector", self.selector), ("section", self.section)):
            if value is not None and (not value.strip() or len(value) > 500):
                raise ValueError(f"evidence_{field_name}_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source.as_dict(),
            "selector": self.selector,
            "section": self.section,
            "raw_text": self.raw_text,
            "extraction_method": self.extraction_method,
            "parser_version": self.parser_version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> EvidenceFragment:
        return cls(
            source=SourceReference.from_dict(
                _mapping(value.get("source"), "evidence_source_invalid")
            ),
            selector=_optional_string(value, "selector"),
            section=_optional_string(value, "section"),
            raw_text=_required_string(value, "raw_text"),
            extraction_method=_required_string(value, "extraction_method"),
            parser_version=_required_string(value, "parser_version"),
        )


@dataclass(frozen=True, slots=True)
class ExtractionWarning:
    code: str
    message: str
    evidence: tuple[EvidenceFragment, ...] = ()

    def __post_init__(self) -> None:
        if _WARNING_CODE.fullmatch(self.code) is None:
            raise ValueError("extraction_warning_code_invalid")
        if not self.message.strip() or len(self.message) > 1_000:
            raise ValueError("extraction_warning_message_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "evidence": [item.as_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ExtractionWarning:
        return cls(
            code=_required_string(value, "code"),
            message=_required_string(value, "message"),
            evidence=tuple(
                EvidenceFragment.from_dict(_mapping(item, "warning_evidence_invalid"))
                for item in _object_list(value, "evidence")
            ),
        )


@dataclass(frozen=True, slots=True)
class SourceArtifactMetadata:
    source: SourceReference
    media_type: str
    content_sha256: str
    byte_length: int
    acquired_at: datetime

    def __post_init__(self) -> None:
        if _MEDIA_TYPE.fullmatch(self.media_type) is None:
            raise ValueError("source_artifact_media_type_invalid")
        if _SHA256.fullmatch(self.content_sha256) is None:
            raise ValueError("source_artifact_sha256_invalid")
        if self.byte_length < 0:
            raise ValueError("source_artifact_byte_length_invalid")
        _aware(self.acquired_at, "source_artifact_acquired_at")

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source.as_dict(),
            "media_type": self.media_type,
            "content_sha256": self.content_sha256,
            "byte_length": self.byte_length,
            "acquired_at": self.acquired_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> SourceArtifactMetadata:
        byte_length = value.get("byte_length")
        acquired_at = value.get("acquired_at")
        if not isinstance(byte_length, int) or isinstance(byte_length, bool):
            raise ValueError("source_artifact_byte_length_invalid")
        if not isinstance(acquired_at, str):
            raise ValueError("source_artifact_acquired_at_invalid")
        return cls(
            source=SourceReference.from_dict(
                _mapping(value.get("source"), "source_artifact_source_invalid")
            ),
            media_type=_required_string(value, "media_type"),
            content_sha256=_required_string(value, "content_sha256"),
            byte_length=byte_length,
            acquired_at=datetime.fromisoformat(acquired_at),
        )
