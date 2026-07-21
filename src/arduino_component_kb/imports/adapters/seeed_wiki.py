"""Tolerant, non-executing Seeed Studio Wiki repository adapter."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import quote

from arduino_component_kb.imports.adapters.markdown import (
    key_values,
    links,
    load_markdown,
    normalize_unit,
    paragraph,
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
from arduino_component_kb.imports.specifications import canonical_specification

_REPOSITORY = "https://github.com/Seeed-Studio/wiki-documents"
_SECTION_ALIASES = {
    "specifications": {"specifications", "specification", "technical specifications", "parameters"},
    "features": {"features", "feature", "key features"},
    "hardware": {"hardware overview", "hardware", "overview", "hardware description"},
    "pinout": {"pinout", "pin map", "pin definition", "pins"},
    "usage": {
        "usage",
        "getting started",
        "how to use",
        "play with arduino",
        "getting started with arduino",
    },
    "resources": {"resources", "resource", "downloads", "documents", "references"},
}


class SeeedWikiAdapter:
    source_key = "seeed_wiki"
    repository_url = _REPOSITORY
    parser_name = "seeed-wiki-git-v1"
    parser_version = "1.1.0"

    async def validate_revision(self, revision: str) -> str:
        return require_commit_sha(revision)

    async def discover(
        self, snapshot: RepositorySnapshot, *, query: str | None = None, limit: int = 100
    ) -> tuple[RepositoryEntry, ...]:
        self._validate_snapshot(snapshot)
        needle = (query or "").strip().casefold()
        entries: list[RepositoryEntry] = []
        for path in sorted(snapshot.files):
            if PurePosixPath(path).suffix.casefold() not in {".md", ".mdx"}:
                continue
            if needle and needle not in path.casefold():
                continue
            title: str | None = None
            try:
                document = load_markdown(snapshot.read(path))
                title = document.metadata.get("title")
                if title is None and document.sections:
                    title = document.sections[0].heading
            except ValueError:
                pass
            entries.append(RepositoryEntry(path, title=title))
            if len(entries) >= min(max(limit, 1), 500):
                break
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
        suffix = PurePosixPath(entry.file_path).suffix.casefold()
        if suffix not in {".md", ".mdx"}:
            return self._result(
                snapshot,
                entry,
                parsed_at,
                source_tag,
                ParseStatus.UNSUPPORTED_DOCUMENT,
                {},
                {},
                ("unsupported_document_type",),
            )
        try:
            document = load_markdown(snapshot.read(entry.file_path))
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
        warnings = list(document.warnings)
        sections: dict[str, list[tuple[str, tuple[str, ...], int]]] = {}
        h1_title: str | None = None
        h1_line = 1
        for section in document.sections:
            if h1_title is None:
                h1_title = section.heading
                h1_line = section.line_number
            kind = self._section_kind(section.heading)
            if kind is None:
                if section.heading != h1_title and any(line.strip() for line in section.lines):
                    warnings.append(f"unknown_section:{section.heading[:80]}")
                continue
            sections.setdefault(kind, []).append(
                (section.heading, section.lines, section.line_number)
            )
        title = (document.metadata.get("title") or h1_title or "").strip()[:160]
        if not title:
            return self._result(
                snapshot,
                entry,
                parsed_at,
                source_tag,
                ParseStatus.INVALID_METADATA,
                {},
                {},
                tuple((*warnings, "title_missing")),
            )
        summary = document.metadata.get("description")
        summary_section = "frontmatter.description"
        if not summary:
            candidates = [document.preamble]
            if document.sections:
                candidates.append(document.sections[0].lines)
            summary = next((value for lines in candidates if (value := paragraph(lines))), None)
            summary_section = "introductory paragraph"
        if not summary:
            summary = f"Technical facts imported from the Seeed Studio Wiki entry {title}."
            summary_section = "generated fallback"
            warnings.append("summary_generated")
        summary = summary[:500]
        specifications: list[dict[str, str]] = []
        specification_provenance: list[FieldProvenance] = []
        ignored_specifications = False
        seen_specifications: set[str] = set()
        for kind in ("specifications", "hardware", "features"):
            for heading, lines, line_number in sections.get(kind, []):
                for key, value in key_values(lines):
                    specification = canonical_specification(key, normalize_unit(value))
                    if specification is None:
                        ignored_specifications = True
                        continue
                    if specification.key in seen_specifications:
                        ignored_specifications = True
                        continue
                    seen_specifications.add(specification.key)
                    specifications.append(
                        {
                            "key": specification.key,
                            "label": specification.label,
                            "value": specification.value[:300],
                        }
                    )
                    specification_provenance.append(
                        self._provenance(
                            snapshot,
                            entry,
                            f"{heading} line {line_number}",
                            Confidence.HIGH,
                            "table_or_key_value_normalization",
                        )
                    )
        if ignored_specifications:
            warnings.append("untrusted_specification_ignored")
        resources: list[dict[str, str]] = []
        resource_provenance: list[FieldProvenance] = []
        for heading, lines, line_number in sections.get("resources", []):
            for label, url in links(lines):
                if any(
                    token in label.casefold() or token in url.casefold()
                    for token in ("datasheet", "library", "schematic")
                ):
                    resources.append({"label": label[:160], "url": url[:1000]})
                    resource_provenance.append(
                        self._provenance(
                            snapshot,
                            entry,
                            f"{heading} line {line_number}",
                            Confidence.HIGH,
                            "url_metadata_only",
                        )
                    )
        fields: dict[str, object] = {
            "title": title,
            "summary": summary,
            "description": summary,
            "category_hint": self._category(title, entry.file_path),
        }
        provenance: dict[str, tuple[FieldProvenance, ...]] = {
            "title": (
                self._provenance(
                    snapshot,
                    entry,
                    "frontmatter.title"
                    if document.metadata.get("title")
                    else f"heading line {h1_line}",
                    Confidence.HIGH,
                    "whitespace_normalization",
                ),
            ),
            "summary": (
                self._provenance(
                    snapshot,
                    entry,
                    summary_section,
                    Confidence.MEDIUM,
                    "limited_summary_extraction",
                ),
            ),
            "description": (
                self._provenance(
                    snapshot, entry, summary_section, Confidence.MEDIUM, "limited_summary_reuse"
                ),
            ),
            "category_hint": (
                self._provenance(
                    snapshot, entry, "title and file path", Confidence.LOW, "keyword_classification"
                ),
            ),
        }
        if specifications:
            fields["specifications"] = specifications
            provenance["specifications"] = tuple(specification_provenance)
        if resources:
            fields["resource_links"] = resources
            provenance["resource_links"] = tuple(resource_provenance)
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

    def _section_kind(self, heading: str) -> str | None:
        normalized = heading.strip().casefold().rstrip(":")
        return next(
            (kind for kind, aliases in _SECTION_ALIASES.items() if normalized in aliases), None
        )

    def _category(self, title: str, path: str) -> str:
        file_name = PurePosixPath(path).stem.replace("_", " ")
        primary = f"{title} {file_name}".casefold()
        rules = (
            (("relay", "motor", "servo", "solenoid", "pump", "actuator", "buzzer"), "actuators"),
            (("button", "switch", "joystick", "keypad", "encoder", "potentiometer"), "input"),
            (("display", "oled", "lcd", "e ink", "epaper", "screen"), "displays"),
            (("battery", "charger", "power supply", "dc dc", "converter"), "power"),
            (
                ("wifi", "bluetooth", "lora", "can bus", "ethernet", "communication"),
                "communication",
            ),
            (("board", "shield", "seeeduino", "wio terminal"), "boards"),
            (
                (
                    "sensor",
                    "temperature",
                    "humidity",
                    "light",
                    "ultrasonic",
                    "distance",
                    "proximity",
                    "accelerometer",
                    "gyroscope",
                    "pressure",
                    "sound",
                    "gas",
                ),
                "sensors",
            ),
        )
        for tokens, category in rules:
            if any(token in primary for token in tokens):
                return category
        path_parts = " ".join(reversed(PurePosixPath(path).parts[-4:-1])).casefold()
        for tokens, category in rules:
            if any(token in path_parts for token in tokens):
                return category
        return "other"

    def _provenance(
        self,
        snapshot: RepositorySnapshot,
        entry: RepositoryEntry,
        section: str,
        confidence: Confidence,
        transformation: str,
    ) -> FieldProvenance:
        return FieldProvenance(
            self.repository_url,
            snapshot.revision,
            entry.file_path,
            section,
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
        stem = PurePosixPath(entry.file_path).stem.replace("_", "-").strip("-")
        original = f"https://wiki.seeedstudio.com/{quote(stem)}/"
        attribution = f"Seeed Studio Wiki, {original}, revision {snapshot.revision}"
        return ParsedRepositoryComponent(
            source_key=self.source_key,
            repository_url=self.repository_url,
            source_revision=snapshot.revision,
            source_tag=source_tag,
            source_file_path=entry.file_path,
            source_entry_name=None,
            original_url=original,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            parsed_at=parsed_at,
            status=status,
            normalized_fields=fields,
            provenance=provenance,
            license_snapshot=LicenseSnapshot(
                "GNU General Public License v3.0 only",
                "GPL-3.0-only",
                "https://www.gnu.org/licenses/gpl-3.0.html",
                attribution,
            ),
            modifications_notice=(
                "Facts extracted; text shortened and units normalized. "
                "Images, code and attachments were excluded."
            ),
            warnings=warnings,
        )
