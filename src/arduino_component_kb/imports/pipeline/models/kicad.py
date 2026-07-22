"""Immutable KiCad index records and pre-matcher search results."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256

from arduino_component_kb.imports.pipeline.models.component_identity import ComponentIdentity
from arduino_component_kb.imports.pipeline.models.normalized_facts import NormalizedFacts

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")


def _mapping(value: object, code: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(code)
    return value


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


def _required_bool(value: Mapping[str, object], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ValueError(f"{key}_must_be_boolean")
    return item


def _required_int(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(f"{key}_must_be_integer")
    return item


def _object_list(value: Mapping[str, object], key: str) -> list[object]:
    items = value.get(key, [])
    if not isinstance(items, list):
        raise ValueError(f"{key}_must_be_array")
    return list(items)


def _string_list(value: Mapping[str, object], key: str) -> tuple[str, ...]:
    items = value.get(key, [])
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise ValueError(f"{key}_must_be_string_array")
    return tuple(items)


def _bounded(value: str, code: str, maximum: int = 2_000) -> str:
    if not value.strip() or "\x00" in value or len(value) > maximum:
        raise ValueError(code)
    return value


@dataclass(frozen=True, slots=True)
class KicadPin:
    number: str
    name: str
    electrical_type: str
    unit: int

    def __post_init__(self) -> None:
        _bounded(self.number, "kicad_pin_number_invalid", 160)
        _bounded(self.name, "kicad_pin_name_invalid", 300)
        _bounded(self.electrical_type, "kicad_pin_electrical_type_invalid", 80)
        if not 1 <= self.unit <= 1_000:
            raise ValueError("kicad_pin_unit_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "number": self.number,
            "name": self.name,
            "electrical_type": self.electrical_type,
            "unit": self.unit,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> KicadPin:
        return cls(
            _required_string(value, "number"),
            _required_string(value, "name"),
            _required_string(value, "electrical_type"),
            _required_int(value, "unit"),
        )


@dataclass(frozen=True, slots=True)
class KicadSymbolRecord:
    library: str
    symbol_name: str
    aliases: tuple[str, ...]
    normalized_names: tuple[str, ...]
    description: str | None
    keywords: tuple[str, ...]
    manufacturer_hints: tuple[str, ...]
    datasheet: str | None
    pins: tuple[KicadPin, ...]
    footprint_filters: tuple[str, ...]
    source_path: str
    source_revision: str
    source_content_sha256: str
    parser_version: str
    is_generic: bool = False

    def __post_init__(self) -> None:
        _bounded(self.library, "kicad_record_library_invalid", 300)
        _bounded(self.symbol_name, "kicad_record_symbol_invalid", 500)
        _bounded(self.source_path, "kicad_record_source_path_invalid", 1_000)
        _bounded(self.parser_version, "kicad_record_parser_version_invalid", 40)
        if _REVISION.fullmatch(self.source_revision) is None:
            raise ValueError("kicad_record_revision_invalid")
        if _SHA256.fullmatch(self.source_content_sha256) is None:
            raise ValueError("kicad_record_content_sha256_invalid")
        if self.description is not None:
            _bounded(self.description, "kicad_record_description_invalid", 10_000)
        if self.datasheet is not None:
            _bounded(self.datasheet, "kicad_record_datasheet_invalid", 2_000)
        for values, code, maximum in (
            (self.aliases, "kicad_record_alias_invalid", 500),
            (self.normalized_names, "kicad_record_normalized_name_invalid", 500),
            (self.keywords, "kicad_record_keyword_invalid", 200),
            (self.manufacturer_hints, "kicad_record_manufacturer_invalid", 300),
            (self.footprint_filters, "kicad_record_footprint_filter_invalid", 500),
        ):
            if any(not item.strip() or "\x00" in item or len(item) > maximum for item in values):
                raise ValueError(code)
            if len(set(values)) != len(values):
                raise ValueError(f"{code}_duplicate")
        if not self.normalized_names:
            raise ValueError("kicad_record_normalized_names_missing")

    @property
    def record_id(self) -> str:
        return f"{self.library}:{self.symbol_name}"

    def as_dict(self) -> dict[str, object]:
        return {
            "library": self.library,
            "symbol_name": self.symbol_name,
            "aliases": list(self.aliases),
            "normalized_names": list(self.normalized_names),
            "description": self.description,
            "keywords": list(self.keywords),
            "manufacturer_hints": list(self.manufacturer_hints),
            "datasheet": self.datasheet,
            "pins": [item.as_dict() for item in self.pins],
            "footprint_filters": list(self.footprint_filters),
            "source_path": self.source_path,
            "source_revision": self.source_revision,
            "source_content_sha256": self.source_content_sha256,
            "parser_version": self.parser_version,
            "is_generic": self.is_generic,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> KicadSymbolRecord:
        return cls(
            library=_required_string(value, "library"),
            symbol_name=_required_string(value, "symbol_name"),
            aliases=_string_list(value, "aliases"),
            normalized_names=_string_list(value, "normalized_names"),
            description=_optional_string(value, "description"),
            keywords=_string_list(value, "keywords"),
            manufacturer_hints=_string_list(value, "manufacturer_hints"),
            datasheet=_optional_string(value, "datasheet"),
            pins=tuple(
                KicadPin.from_dict(_mapping(item, "kicad_pin_invalid"))
                for item in _object_list(value, "pins")
            ),
            footprint_filters=_string_list(value, "footprint_filters"),
            source_path=_required_string(value, "source_path"),
            source_revision=_required_string(value, "source_revision"),
            source_content_sha256=_required_string(value, "source_content_sha256"),
            parser_version=_required_string(value, "parser_version"),
            is_generic=_required_bool(value, "is_generic"),
        )


class KicadMatchBasis(StrEnum):
    EXACT_PART_NUMBER = "exact_part_number"
    ALIAS = "alias"
    NORMALIZED_NAME = "normalized_name"
    DESCRIPTION = "description"
    MANUFACTURER_HINT = "manufacturer_hint"


@dataclass(frozen=True, slots=True)
class KicadMatchedTerm:
    basis: KicadMatchBasis
    query: str
    matched_value: str

    def __post_init__(self) -> None:
        _bounded(self.query, "kicad_match_query_invalid", 500)
        _bounded(self.matched_value, "kicad_match_value_invalid", 2_000)

    def as_dict(self) -> dict[str, str]:
        return {
            "basis": self.basis.value,
            "query": self.query,
            "matched_value": self.matched_value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> KicadMatchedTerm:
        return cls(
            KicadMatchBasis(_required_string(value, "basis")),
            _required_string(value, "query"),
            _required_string(value, "matched_value"),
        )


@dataclass(frozen=True, slots=True)
class KicadSearchHit:
    record: KicadSymbolRecord
    matched_terms: tuple[KicadMatchedTerm, ...]

    def __post_init__(self) -> None:
        if not self.matched_terms:
            raise ValueError("kicad_search_hit_terms_missing")
        if len(set(self.matched_terms)) != len(self.matched_terms):
            raise ValueError("kicad_search_hit_terms_duplicate")

    def as_dict(self) -> dict[str, object]:
        return {
            "record": self.record.as_dict(),
            "matched_terms": [item.as_dict() for item in self.matched_terms],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> KicadSearchHit:
        return cls(
            KicadSymbolRecord.from_dict(_mapping(value.get("record"), "kicad_record_invalid")),
            tuple(
                KicadMatchedTerm.from_dict(_mapping(item, "kicad_matched_term_invalid"))
                for item in _object_list(value, "matched_terms")
            ),
        )


@dataclass(frozen=True, slots=True)
class KicadEnrichmentRequest:
    identity: ComponentIdentity
    facts: NormalizedFacts

    def __post_init__(self) -> None:
        if self.identity.normalized_facts != self.facts:
            raise ValueError("kicad_enrichment_facts_mismatch")


@dataclass(frozen=True, slots=True)
class KicadCandidateSet:
    identity_sha256: str
    index_sha256: str
    index_revision: str
    hits: tuple[KicadSearchHit, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.identity_sha256) is None:
            raise ValueError("kicad_candidate_identity_sha256_invalid")
        if _SHA256.fullmatch(self.index_sha256) is None:
            raise ValueError("kicad_candidate_index_sha256_invalid")
        if _REVISION.fullmatch(self.index_revision) is None:
            raise ValueError("kicad_candidate_index_revision_invalid")
        record_ids = [item.record.record_id for item in self.hits]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("kicad_candidate_hits_duplicate")
        if any(not item or len(item) > 160 for item in self.warnings):
            raise ValueError("kicad_candidate_warning_invalid")
        if len(set(self.warnings)) != len(self.warnings):
            raise ValueError("kicad_candidate_warnings_duplicate")

    def as_dict(self) -> dict[str, object]:
        return {
            "identity_sha256": self.identity_sha256,
            "index_sha256": self.index_sha256,
            "index_revision": self.index_revision,
            "hits": [item.as_dict() for item in self.hits],
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> KicadCandidateSet:
        return cls(
            identity_sha256=_required_string(value, "identity_sha256"),
            index_sha256=_required_string(value, "index_sha256"),
            index_revision=_required_string(value, "index_revision"),
            hits=tuple(
                KicadSearchHit.from_dict(_mapping(item, "kicad_search_hit_invalid"))
                for item in _object_list(value, "hits")
            ),
            warnings=_string_list(value, "warnings"),
        )

    @classmethod
    def from_json(cls, value: str) -> KicadCandidateSet:
        decoded: object = json.loads(value)
        return cls.from_dict(_mapping(decoded, "kicad_candidate_set_invalid"))


@dataclass(frozen=True, slots=True)
class KicadSymbolIndex:
    records: tuple[KicadSymbolRecord, ...]
    source_revision: str
    _exact: dict[str, tuple[int, ...]] = field(init=False, repr=False, compare=False)
    _aliases: dict[str, tuple[int, ...]] = field(init=False, repr=False, compare=False)
    _names: dict[str, tuple[int, ...]] = field(init=False, repr=False, compare=False)
    _description_tokens: dict[str, tuple[int, ...]] = field(init=False, repr=False, compare=False)
    _manufacturers: dict[str, tuple[int, ...]] = field(init=False, repr=False, compare=False)
    _index_sha256: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if _REVISION.fullmatch(self.source_revision) is None:
            raise ValueError("kicad_index_revision_invalid")
        if any(item.source_revision != self.source_revision for item in self.records):
            raise ValueError("kicad_index_record_revision_mismatch")
        record_ids = [item.record_id for item in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("kicad_index_record_duplicate")
        object.__setattr__(self, "_exact", self._build_map(self._exact_values))
        object.__setattr__(self, "_aliases", self._build_map(lambda item: item.aliases))
        object.__setattr__(
            self,
            "_names",
            self._build_map(lambda item: item.normalized_names, _name_key),
        )
        object.__setattr__(
            self,
            "_description_tokens",
            self._build_map(
                lambda item: _tokens(" ".join((item.description or "", *item.keywords)))
            ),
        )
        object.__setattr__(
            self,
            "_manufacturers",
            self._build_map(lambda item: item.manufacturer_hints, _name_key),
        )
        payload = json.dumps(
            [item.as_dict() for item in self.records],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        object.__setattr__(self, "_index_sha256", sha256(payload.encode()).hexdigest())

    @property
    def index_sha256(self) -> str:
        return self._index_sha256

    def exact_part_number(self, value: str) -> tuple[KicadSymbolRecord, ...]:
        return self._records(self._exact.get(_exact_key(value), ()))

    def alias(self, value: str) -> tuple[KicadSymbolRecord, ...]:
        return self._records(self._aliases.get(_exact_key(value), ()))

    def normalized_name(self, value: str) -> tuple[KicadSymbolRecord, ...]:
        return self._records(self._names.get(_name_key(value), ()))

    def description(self, value: str, limit: int = 50) -> tuple[KicadSymbolRecord, ...]:
        if not 1 <= limit <= 200:
            raise ValueError("kicad_description_limit_invalid")
        query_tokens = _tokens(value)
        counts: dict[int, int] = {}
        for token in query_tokens:
            for index in self._description_tokens.get(token, ()):
                counts[index] = counts.get(index, 0) + 1
        ranked = sorted(counts, key=lambda index: (-counts[index], self.records[index].record_id))
        return self._records(tuple(ranked[:limit]))

    def manufacturer_hint(self, value: str) -> tuple[KicadSymbolRecord, ...]:
        return self._records(self._manufacturers.get(_name_key(value), ()))

    def _build_map(
        self,
        values: Callable[[KicadSymbolRecord], tuple[str, ...]],
        keyer: Callable[[str], str] | None = None,
    ) -> dict[str, tuple[int, ...]]:
        mutable: dict[str, list[int]] = {}
        resolved_keyer = keyer or _exact_key
        for index, record in enumerate(self.records):
            record_values = values(record)
            for value in record_values:
                key = resolved_keyer(value)
                mutable.setdefault(key, []).append(index)
        return {key: tuple(indexes) for key, indexes in mutable.items()}

    @staticmethod
    def _exact_values(record: KicadSymbolRecord) -> tuple[str, ...]:
        return (record.symbol_name,)

    def _records(self, indexes: tuple[int, ...]) -> tuple[KicadSymbolRecord, ...]:
        return tuple(self.records[index] for index in indexes)


def _exact_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _text_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", normalized)).strip()


def _tokens(value: str) -> tuple[str, ...]:
    ignored = {"a", "an", "and", "for", "grove", "module", "of", "the", "with"}
    return tuple(
        dict.fromkeys(
            token for token in _text_key(value).split() if len(token) >= 2 and token not in ignored
        )
    )
