"""Safe, incremental index builder for official KiCad symbol libraries."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import PurePosixPath
from time import perf_counter
from typing import Protocol

from arduino_component_kb.imports.adapters.sexpr import (
    SExpression,
    child_lists,
    child_value,
    head,
    parse_sexpression,
)
from arduino_component_kb.imports.pipeline.models import (
    KicadPin,
    KicadSymbolIndex,
    KicadSymbolRecord,
)
from arduino_component_kb.imports.repository_domain import normalize_repository_url

KICAD_REPOSITORY_URL = "https://gitlab.com/kicad/libraries/kicad-symbols"
DEFAULT_KICAD_LIBRARY_ALLOWLIST = (
    "Sensor_",
    "MCU_",
    "Display_",
    "74xx",
    "Relay",
    "Switch",
    "Connector",
    "Motor",
    "Driver_Motor",
    "Regulator_",
    "Transistor_",
    "Transistor_Array",
    "Timer",
    "Diode",
    "LED",
    "Memory",
    "Interface_",
)
_ELECTRICAL_TYPES = frozenset(
    {
        "input",
        "output",
        "bidirectional",
        "tri_state",
        "passive",
        "free",
        "unspecified",
        "power_in",
        "power_out",
        "open_collector",
        "open_emitter",
        "no_connect",
    }
)
_UNIT_SUFFIX = re.compile(r"_(?P<unit>[1-9][0-9]*)_(?P<convert>[0-9]+)$")
_GENERIC_NAMES = frozenset(
    {"c", "capacitor", "connector", "crystal", "jumper", "l", "led", "r", "resistor"}
)


class Timer(Protocol):
    def now(self) -> float: ...


class KicadIndexSnapshot(Protocol):
    @property
    def repository_url(self) -> str: ...

    @property
    def revision(self) -> str: ...

    @property
    def files(self) -> Mapping[str, bytes]: ...


class PerformanceTimer:
    def now(self) -> float:
        return perf_counter()


@dataclass(frozen=True, slots=True)
class CachedKicadLibrary:
    source_path: str
    content_sha256: str
    records: tuple[KicadSymbolRecord, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KicadIndexCache:
    source_revision: str
    libraries: tuple[CachedKicadLibrary, ...]
    index: KicadSymbolIndex
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KicadIndexBuildStats:
    parsed_files: int
    reused_files: int
    removed_files: int
    symbol_count: int
    cache_hit: bool
    duration_ms: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KicadIndexBuildResult:
    index: KicadSymbolIndex
    stats: KicadIndexBuildStats


class KicadSymbolIndexer:
    parser_version = "kicad-index-v1.0.0"

    def __init__(
        self,
        library_allowlist: tuple[str, ...] = DEFAULT_KICAD_LIBRARY_ALLOWLIST,
        timer: Timer | None = None,
    ) -> None:
        if (
            not library_allowlist
            or len(library_allowlist) > 50
            or any(
                not value or len(value) > 80 or "/" in value or "\\" in value
                for value in library_allowlist
            )
        ):
            raise ValueError("kicad_index_allowlist_invalid")
        self.library_allowlist = library_allowlist
        self.timer = timer or PerformanceTimer()
        self._cache: KicadIndexCache | None = None

    @property
    def cache(self) -> KicadIndexCache | None:
        return self._cache

    def build(self, snapshot: KicadIndexSnapshot) -> KicadIndexBuildResult:
        started = self.timer.now()
        if normalize_repository_url(snapshot.repository_url) != KICAD_REPOSITORY_URL:
            raise ValueError("kicad_index_repository_invalid")
        source_files = {
            path: content
            for path, content in snapshot.files.items()
            if path.endswith(".kicad_sym") and self._library_allowed(path)
        }
        digests = {path: sha256(content).hexdigest() for path, content in source_files.items()}
        previous = {item.source_path: item for item in self._cache.libraries} if self._cache else {}
        if (
            self._cache is not None
            and self._cache.source_revision == snapshot.revision
            and {path: item.content_sha256 for path, item in previous.items()} == digests
        ):
            duration = (self.timer.now() - started) * 1_000
            return KicadIndexBuildResult(
                self._cache.index,
                KicadIndexBuildStats(
                    0,
                    len(source_files),
                    0,
                    len(self._cache.index.records),
                    True,
                    duration,
                    self._cache.warnings,
                ),
            )

        parsed_files = 0
        reused_files = 0
        warnings: list[str] = []
        libraries: list[CachedKicadLibrary] = []
        records: list[KicadSymbolRecord] = []
        for path in sorted(source_files):
            digest = digests[path]
            cached = previous.get(path)
            if cached is not None and cached.content_sha256 == digest:
                current_records = tuple(
                    replace(item, source_revision=snapshot.revision) for item in cached.records
                )
                current_warnings = cached.warnings
                reused_files += 1
            else:
                parsed_files += 1
                try:
                    current_records, current_warnings = self._parse_library(
                        path,
                        source_files[path],
                        snapshot.revision,
                        digest,
                    )
                except ValueError as error:
                    current_records = ()
                    current_warnings = (f"{path}:{_safe_code(error)}",)
            warnings.extend(current_warnings)
            libraries.append(CachedKicadLibrary(path, digest, current_records, current_warnings))
            records.extend(current_records)
        index = KicadSymbolIndex(
            tuple(sorted(records, key=lambda item: item.record_id)),
            snapshot.revision,
        )
        stable_warnings = tuple(dict.fromkeys(warnings))
        self._cache = KicadIndexCache(
            snapshot.revision,
            tuple(libraries),
            index,
            stable_warnings,
        )
        removed_files = len(set(previous).difference(source_files))
        duration = (self.timer.now() - started) * 1_000
        return KicadIndexBuildResult(
            index,
            KicadIndexBuildStats(
                parsed_files,
                reused_files,
                removed_files,
                len(index.records),
                False,
                duration,
                stable_warnings,
            ),
        )

    def _parse_library(
        self,
        path: str,
        content: bytes,
        revision: str,
        digest: str,
    ) -> tuple[tuple[KicadSymbolRecord, ...], tuple[str, ...]]:
        root = parse_sexpression(content)
        if head(root) != "kicad_symbol_lib":
            raise ValueError("kicad_root_missing")
        library = self._library_name(path)
        records: list[KicadSymbolRecord] = []
        warnings: list[str] = []
        for symbol in child_lists(root, "symbol"):
            name = _list_atom(symbol, 1)
            if name is None:
                warnings.append(f"{path}:symbol_name_missing")
                continue
            properties = self._properties(symbol)
            aliases = self._aliases(symbol, properties, name)
            pins, pin_warnings = self._pins(symbol, name)
            warnings.extend(f"{path}:{name}:{warning}" for warning in pin_warnings)
            filters = tuple(
                dict.fromkeys(
                    value
                    for group in child_lists(symbol, "footprint_filters")
                    for item in group.children[1:]
                    if (value := item.atom) is not None and value.strip()
                )
            )
            description = properties.get("Description") or None
            datasheet = properties.get("Datasheet") or None
            if datasheet in {"~", "-"}:
                datasheet = None
            keywords = _split_values(properties.get("ki_keywords", ""), whitespace=True)
            manufacturers = tuple(
                dict.fromkeys(
                    value
                    for key in ("Manufacturer", "Manufacturer_Name", "ki_manufacturer")
                    if (value := properties.get(key)) is not None and value.strip()
                )
            )
            normalized_names = tuple(
                dict.fromkeys(
                    value for candidate in (name, *aliases) if (value := _name_key(candidate))
                )
            )
            records.append(
                KicadSymbolRecord(
                    library=library,
                    symbol_name=name,
                    aliases=aliases,
                    normalized_names=normalized_names,
                    description=description,
                    keywords=keywords,
                    manufacturer_hints=manufacturers,
                    datasheet=datasheet,
                    pins=pins,
                    footprint_filters=filters,
                    source_path=path,
                    source_revision=revision,
                    source_content_sha256=digest,
                    parser_version=self.parser_version,
                    is_generic=_is_generic(name),
                )
            )
        return tuple(records), tuple(warnings)

    @staticmethod
    def _properties(symbol: SExpression) -> dict[str, str]:
        result: dict[str, str] = {}
        for prop in child_lists(symbol, "property"):
            key, value = _list_atom(prop, 1), _list_atom(prop, 2)
            if key is not None and value is not None:
                result[key] = value
        return result

    @staticmethod
    def _aliases(
        symbol: SExpression, properties: dict[str, str], symbol_name: str
    ) -> tuple[str, ...]:
        candidates: list[str] = []
        value = properties.get("Value")
        if value and value != symbol_name:
            candidates.append(value)
        for key in ("Aliases", "ki_aliases"):
            candidates.extend(_split_values(properties.get(key, ""), whitespace=False))
        extends = child_value(symbol, "extends")
        if extends:
            candidates.append(extends)
        return tuple(dict.fromkeys(item for item in candidates if item.strip()))

    @staticmethod
    def _pins(
        symbol: SExpression, symbol_name: str
    ) -> tuple[tuple[KicadPin, ...], tuple[str, ...]]:
        collected: list[tuple[SExpression, int]] = [(pin, 1) for pin in child_lists(symbol, "pin")]
        for nested in child_lists(symbol, "symbol"):
            nested_name = _list_atom(nested, 1) or symbol_name
            match = _UNIT_SUFFIX.search(nested_name)
            unit = int(match.group("unit")) if match else 1
            collected.extend((pin, unit) for pin in child_lists(nested, "pin"))
        pins: list[KicadPin] = []
        warnings: list[str] = []
        for pin, unit in collected:
            electrical = _list_atom(pin, 1) or "unspecified"
            if electrical not in _ELECTRICAL_TYPES:
                warnings.append(f"unknown_electrical_type:{electrical[:80]}")
            number = child_value(pin, "number")
            name = child_value(pin, "name")
            if not number or not name:
                warnings.append("pin_identity_missing")
                continue
            pins.append(KicadPin(number, name, electrical, unit))
        return tuple(pins), tuple(dict.fromkeys(warnings))

    def _library_allowed(self, path: str) -> bool:
        library = self._library_name(path)
        return any(
            library == prefix or library.startswith(prefix) for prefix in self.library_allowlist
        )

    @staticmethod
    def _library_name(path: str) -> str:
        parts = PurePosixPath(path).parts
        directory = next((part[:-13] for part in parts if part.endswith(".kicad_symdir")), None)
        return directory or PurePosixPath(path).stem


def _list_atom(expression: SExpression, index: int) -> str | None:
    children = expression.children
    return children[index].atom if len(children) > index else None


def _split_values(value: str, *, whitespace: bool) -> tuple[str, ...]:
    separator = r"[\s,;|]+" if whitespace else r"[,;|]+"
    return tuple(dict.fromkeys(item.strip() for item in re.split(separator, value) if item.strip()))


def _name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", normalized)).strip()


def _is_generic(value: str) -> bool:
    normalized = _name_key(value)
    first = normalized.split(" ", 1)[0]
    return (
        normalized in _GENERIC_NAMES
        or first
        in {"c", "capacitor", "connector", "crystal", "jumper", "l", "led", "r", "resistor"}
        or normalized.startswith("connector generic")
        or re.fullmatch(r"conn(?:ector)? \d+x\d+", normalized) is not None
    )


def _safe_code(error: ValueError) -> str:
    value = str(error)
    return value if re.fullmatch(r"[a-z][a-z0-9_]{0,79}", value) else "kicad_parse_failed"
