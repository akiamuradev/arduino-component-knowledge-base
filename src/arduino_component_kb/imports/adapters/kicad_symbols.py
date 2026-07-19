"""Safe parser for allowlisted official KiCad `.kicad_sym` entries."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import quote

from arduino_component_kb.imports.adapters.sexpr import (
    SExpression,
    child_lists,
    child_value,
    head,
    parse_sexpression,
)
from arduino_component_kb.imports.repository_domain import (
    Confidence,
    FieldProvenance,
    LicenseSnapshot,
    ParsedRepositoryComponent,
    ParseStatus,
    RepositoryEntry,
    RepositorySnapshot,
    normalize_repository_url,
    require_commit_sha,
)

_REPOSITORY = "https://gitlab.com/kicad/libraries/kicad-symbols"
DEFAULT_LIBRARY_ALLOWLIST = (
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


class KicadSymbolsAdapter:
    source_key = "kicad_symbols"
    repository_url = _REPOSITORY
    parser_name = "kicad-symbols-v1"
    parser_version = "1.0.0"

    def __init__(self, library_allowlist: tuple[str, ...] = DEFAULT_LIBRARY_ALLOWLIST) -> None:
        if (
            not library_allowlist
            or len(library_allowlist) > 50
            or any(
                not value or len(value) > 80 or "/" in value or "\\" in value
                for value in library_allowlist
            )
        ):
            raise ValueError("kicad_library_allowlist_invalid")
        self.library_allowlist = library_allowlist

    async def validate_revision(self, revision: str) -> str:
        return require_commit_sha(revision)

    async def discover(
        self, snapshot: RepositorySnapshot, *, query: str | None = None, limit: int = 100
    ) -> tuple[RepositoryEntry, ...]:
        self._validate_snapshot(snapshot)
        needle = (query or "").strip().casefold()
        entries: list[RepositoryEntry] = []
        for path in sorted(snapshot.files):
            if not path.endswith(".kicad_sym") or not self._library_allowed(path):
                continue
            try:
                root = parse_sexpression(snapshot.read(path))
            except ValueError:
                continue
            if head(root) != "kicad_symbol_lib":
                continue
            for symbol in child_lists(root, "symbol"):
                name = self._list_atom(symbol, 1)
                if name is None or (needle and needle not in f"{path} {name}".casefold()):
                    continue
                entries.append(RepositoryEntry(path, entry_name=name, title=name))
                if len(entries) >= min(max(limit, 1), 500):
                    return tuple(entries)
        return tuple(entries)

    async def parse_entry(
        self,
        snapshot: RepositorySnapshot,
        entry: RepositoryEntry,
        *,
        parsed_at: datetime,
        source_tag: str | None = None,
    ) -> ParsedRepositoryComponent:
        self._validate_snapshot(snapshot)
        if not entry.file_path.endswith(".kicad_sym") or not self._library_allowed(entry.file_path):
            return self._result(
                snapshot,
                entry,
                parsed_at,
                source_tag,
                ParseStatus.UNSUPPORTED_DOCUMENT,
                {},
                {},
                ("library_not_allowlisted",),
            )
        try:
            root = parse_sexpression(snapshot.read(entry.file_path))
        except ValueError as error:
            return self._result(
                snapshot,
                entry,
                parsed_at,
                source_tag,
                ParseStatus.INVALID_METADATA,
                {},
                {},
                (str(error),),
            )
        if head(root) != "kicad_symbol_lib":
            return self._result(
                snapshot,
                entry,
                parsed_at,
                source_tag,
                ParseStatus.SOURCE_DRIFT,
                {},
                {},
                ("kicad_root_missing",),
            )
        if not entry.entry_name:
            return self._result(
                snapshot,
                entry,
                parsed_at,
                source_tag,
                ParseStatus.INVALID_METADATA,
                {},
                {},
                ("symbol_name_missing",),
            )
        symbols = {
            name: symbol
            for symbol in child_lists(root, "symbol")
            if (name := self._list_atom(symbol, 1)) is not None
        }
        symbol = symbols.get(entry.entry_name)
        if symbol is None:
            return self._result(
                snapshot,
                entry,
                parsed_at,
                source_tag,
                ParseStatus.SOURCE_DRIFT,
                {},
                {},
                ("symbol_not_found",),
            )
        properties: dict[str, str] = {}
        for prop in child_lists(symbol, "property"):
            key, value = self._list_atom(prop, 1), self._list_atom(prop, 2)
            if key is not None and value is not None:
                properties[key] = value
        warnings: list[str] = []
        pins: list[dict[str, object]] = []
        for pin, unit in self._pins(symbol, entry.entry_name):
            electrical = self._list_atom(pin, 1) or "unspecified"
            if electrical not in _ELECTRICAL_TYPES:
                warnings.append(f"unknown_electrical_type:{electrical[:80]}")
            pins.append(
                {
                    "number": child_value(pin, "number") or "",
                    "name": child_value(pin, "name") or "",
                    "electrical_type": electrical,
                    "unit": unit,
                }
            )
        footprint_filters: list[str] = []
        for filters in child_lists(symbol, "footprint_filters"):
            footprint_filters.extend(
                value for item in filters.children[1:] if (value := item.atom) is not None
            )
        library = self._library_name(entry.file_path)
        fields: dict[str, object] = {
            "library_name": library,
            "symbol_name": entry.entry_name,
            "reference": properties.get("Reference", ""),
            "value": properties.get("Value", entry.entry_name),
            "description": properties.get("Description", ""),
            "keywords": properties.get("ki_keywords", ""),
            "footprint": properties.get("Footprint", ""),
            "footprint_filters": footprint_filters,
            "pins": pins,
            "format_version": child_value(root, "version") or "unknown",
        }
        datasheet = properties.get("Datasheet")
        if datasheet:
            fields["datasheet_url"] = datasheet
        extends = child_value(symbol, "extends")
        if extends:
            fields["extends"] = extends
        provenance: dict[str, tuple[FieldProvenance, ...]] = {
            key: (
                self._provenance(
                    snapshot,
                    entry,
                    "pins"
                    if key == "pins"
                    else ("footprint_filters" if key == "footprint_filters" else key),
                    Confidence.HIGH,
                    "s_expression_property_mapping",
                ),
            )
            for key in fields
        }
        status = ParseStatus.PARSED_WITH_WARNINGS if warnings else ParseStatus.PARSED
        return self._result(
            snapshot,
            entry,
            parsed_at,
            source_tag,
            status,
            fields,
            provenance,
            tuple(dict.fromkeys(warnings)),
        )

    def _validate_snapshot(self, snapshot: RepositorySnapshot) -> None:
        if normalize_repository_url(snapshot.repository_url) != self.repository_url:
            raise ValueError("repository_not_registered")
        require_commit_sha(snapshot.revision)

    def _library_name(self, path: str) -> str:
        parts = PurePosixPath(path).parts
        directory = next((part[:-13] for part in parts if part.endswith(".kicad_symdir")), None)
        return directory or PurePosixPath(path).stem

    def _library_allowed(self, path: str) -> bool:
        library = self._library_name(path)
        return any(
            library == prefix or library.startswith(prefix) for prefix in self.library_allowlist
        )

    def _pins(self, symbol: SExpression, symbol_name: str) -> tuple[tuple[SExpression, int], ...]:
        result: list[tuple[SExpression, int]] = [(pin, 1) for pin in child_lists(symbol, "pin")]
        for nested in child_lists(symbol, "symbol"):
            nested_name = self._list_atom(nested, 1) or symbol_name
            match = _UNIT_SUFFIX.search(nested_name)
            unit = int(match.group("unit")) if match else 1
            result.extend((pin, unit) for pin in child_lists(nested, "pin"))
        return tuple(result)

    def _list_atom(self, expression: SExpression, index: int) -> str | None:
        children = expression.children
        return children[index].atom if len(children) > index else None

    def _provenance(
        self,
        snapshot: RepositorySnapshot,
        entry: RepositoryEntry,
        prop: str,
        confidence: Confidence,
        transformation: str,
    ) -> FieldProvenance:
        return FieldProvenance(
            self.repository_url,
            snapshot.revision,
            entry.file_path,
            prop,
            confidence,
            transformation,
        )

    def _result(
        self,
        snapshot: RepositorySnapshot,
        entry: RepositoryEntry,
        parsed_at: datetime,
        source_tag: str | None,
        status: ParseStatus,
        fields: dict[str, object],
        provenance: dict[str, tuple[FieldProvenance, ...]],
        warnings: tuple[str, ...],
    ) -> ParsedRepositoryComponent:
        encoded_path = quote(entry.file_path, safe="/")
        original = f"{self.repository_url}/-/blob/{snapshot.revision}/{encoded_path}"
        if entry.entry_name:
            original += f"#{quote(entry.entry_name)}"
        attribution = (
            f"Official KiCad Libraries, {entry.file_path}:{entry.entry_name or ''}, "
            f"revision {snapshot.revision}"
        )
        return ParsedRepositoryComponent(
            source_key=self.source_key,
            repository_url=self.repository_url,
            source_revision=snapshot.revision,
            source_tag=source_tag,
            source_file_path=entry.file_path,
            source_entry_name=entry.entry_name,
            original_url=original,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            parsed_at=parsed_at,
            status=status,
            normalized_fields=fields,
            provenance=provenance,
            license_snapshot=LicenseSnapshot(
                "Creative Commons Attribution-ShareAlike 4.0 International",
                "CC-BY-SA-4.0",
                "https://gitlab.com/kicad/libraries/kicad-symbols/-/blob/master/LICENSE.md",
                attribution,
            ),
            modifications_notice=(
                "Structured symbol properties and pins transformed into the catalogue format."
            ),
            warnings=warnings,
        )
