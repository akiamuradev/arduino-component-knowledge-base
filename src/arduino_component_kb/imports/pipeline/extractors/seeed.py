"""Evidence-preserving Seeed Wiki extractor for the parallel import pipeline."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Protocol

from arduino_component_kb.imports.pipeline.context import (
    ImportPipelineContext,
    PipelineStage,
    StageExecution,
    StageResult,
)
from arduino_component_kb.imports.pipeline.errors import ParsingError
from arduino_component_kb.imports.pipeline.extractors.markdown import (
    KeyValueFragment,
    MarkdownDocument,
    MarkdownSection,
    clean_inline,
    images,
    key_values,
    links,
    list_items,
    paragraphs,
    parse_markdown,
    table_rows,
)
from arduino_component_kb.imports.pipeline.models import (
    DescriptionSection,
    EvidenceFragment,
    ExtractedFacts,
    ExtractedField,
    ExtractionWarning,
    Identifier,
    IdentifierKind,
    ImageReference,
    ModulePin,
    RawSpecification,
    ResourceKind,
    ResourceReference,
    SourceArtifact,
    UnknownFact,
)

_HEADING_TOKEN = re.compile(r"[^a-z0-9]+")
_LABEL_TOKEN = re.compile(r"[^a-z0-9]+")
_PART_MENTION = re.compile(
    r"\b(?:based on|built around|powered by|uses?)\s+(?:an?\s+)?([A-Z][A-Z0-9._-]{2,31})\b"
)
_NUMBERED_PIN = re.compile(r"^[A-Za-z]*\d+[A-Za-z]*$")

_SECTION_ALIASES: dict[str, frozenset[str]] = {
    "description": frozenset(
        {
            "about",
            "description",
            "introduction",
            "overview",
            "product description",
            "what is it",
        }
    ),
    "features": frozenset({"feature", "features", "key features", "highlights"}),
    "applications": frozenset({"application", "applications", "use cases", "typical applications"}),
    "specifications": frozenset(
        {"parameters", "specification", "specifications", "technical specifications"}
    ),
    "hardware": frozenset(
        {"hardware", "hardware description", "hardware overview", "hardware structure"}
    ),
    "pinout": frozenset({"pin definition", "pin map", "pinout", "pins"}),
    "usage": frozenset(
        {
            "getting started",
            "getting started with arduino",
            "how to use",
            "play with arduino",
            "usage",
        }
    ),
    "resources": frozenset({"documents", "downloads", "references", "resource", "resources"}),
    "identity": frozenset({"part list", "product data", "product information"}),
}

_IDENTIFIER_LABELS = {
    "sku": IdentifierKind.SKU,
    "model": IdentifierKind.MODEL,
    "model number": IdentifierKind.MODEL,
    "part number": IdentifierKind.PART_NUMBER,
    "part no": IdentifierKind.PART_NUMBER,
    "product id": IdentifierKind.PRODUCT_ID,
}
_MANUFACTURER_LABELS = frozenset({"manufacturer", "manufacturer name"})
_BRAND_LABELS = frozenset({"brand", "product family"})
_INTERFACE_LABELS = frozenset(
    {"bus", "communication interface", "interface", "interfaces", "protocol"}
)
_PRIMARY_IC_LABELS = frozenset(
    {
        "chip",
        "controller",
        "main chip",
        "main ic",
        "mcu",
        "microcontroller",
        "primary ic",
        "sensor ic",
    }
)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SeeedFactExtractor:
    parser_name = "seeed-facts-v2"
    parser_version = "2.0.0"

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or SystemClock()

    async def extract(
        self, context: ImportPipelineContext, artifact: SourceArtifact
    ) -> StageResult[ExtractedFacts]:
        started_at = self.clock.now()
        if context.source_key != artifact.metadata.source.source_key:
            raise ParsingError("pipeline_source_mismatch")
        facts = self._extract(artifact)
        completed_at = self.clock.now()
        warning_codes = tuple(dict.fromkeys(warning.code for warning in facts.warnings))
        updated = context.advance(
            StageExecution(
                stage=PipelineStage.EXTRACTION,
                started_at=started_at,
                completed_at=completed_at,
                warnings=warning_codes,
            )
        )
        return StageResult(stage=PipelineStage.EXTRACTION, context=updated, value=facts)

    def _extract(self, artifact: SourceArtifact) -> ExtractedFacts:
        source = artifact.metadata.source
        path = source.source_path or ""
        if source.source_key != "seeed_wiki":
            raise ParsingError("seeed_source_invalid")
        if not path.casefold().endswith((".md", ".mdx")):
            raise ParsingError("seeed_document_type_unsupported")
        if artifact.metadata.media_type not in {"text/markdown", "text/mdx"}:
            raise ParsingError("seeed_media_type_unsupported")
        try:
            document = parse_markdown(artifact.content)
        except ValueError as error:
            raise ParsingError(str(error)) from error

        h1_sections = tuple(section for section in document.sections if section.level == 1)
        warnings = [
            ExtractionWarning(code=code, message=self._warning_message(code))
            for code in document.warnings
        ]
        titles = self._titles(artifact, document, h1_sections)
        if not titles:
            raise ParsingError("seeed_title_missing")
        if len({field.value.casefold() for field in titles}) > 1:
            warnings.append(
                ExtractionWarning(
                    code="ambiguous_title",
                    message="Frontmatter and level-one headings contain different titles.",
                    evidence=tuple(item for field in titles for item in field.evidence),
                )
            )

        grouped: dict[str, list[MarkdownSection]] = {}
        unknown_sections: list[MarkdownSection] = []
        for section in document.sections:
            if section.level == 1:
                continue
            kind = self._section_kind(section.heading)
            if kind is None:
                if self._section_text(section):
                    unknown_sections.append(section)
                continue
            grouped.setdefault(kind, []).append(section)

        summaries = self._summaries(artifact, document, h1_sections)
        descriptions = self._text_sections(artifact, grouped.get("description", []))
        features = self._list_facts(artifact, grouped.get("features", []))
        applications = self._list_facts(artifact, grouped.get("applications", []))
        usage = self._text_sections(artifact, grouped.get("usage", []))
        specifications = self._specifications(
            artifact,
            (
                *grouped.get("specifications", []),
                *grouped.get("hardware", []),
                *grouped.get("features", []),
            ),
        )
        module_pinout = self._module_pinout(artifact, grouped.get("pinout", []))
        resources = self._resources(artifact, grouped.get("resources", []))
        image_facts = self._images(artifact, document)
        all_key_values = tuple(
            (section, fragment)
            for section in document.sections
            for fragment in key_values(section.lines)
        )
        identifiers = self._identifiers(artifact, document, all_key_values)
        manufacturers = self._label_string_facts(artifact, all_key_values, _MANUFACTURER_LABELS)
        brands = self._label_string_facts(artifact, all_key_values, _BRAND_LABELS)
        interfaces = self._label_string_facts(artifact, all_key_values, _INTERFACE_LABELS)
        primary_ics = self._primary_ics(artifact, document, all_key_values)
        unmapped = self._unmapped_sections(artifact, unknown_sections)

        if not summaries:
            warnings.append(
                ExtractionWarning(
                    code="summary_missing",
                    message="No source-backed summary candidate was found.",
                )
            )
        if not descriptions:
            warnings.append(
                ExtractionWarning(
                    code="description_missing",
                    message="No explicit description section was found.",
                )
            )
        if not specifications:
            warnings.append(
                ExtractionWarning(
                    code="specifications_missing",
                    message="No specification rows or key-value facts were found.",
                )
            )
        if not module_pinout:
            warnings.append(
                ExtractionWarning(
                    code="module_pinout_missing",
                    message="No module-level pinout rows were found.",
                )
            )
        warnings.extend(
            ExtractionWarning(
                code="unknown_section",
                message=f"Unmapped section retained: {section.heading}",
                evidence=(
                    self._evidence(
                        artifact,
                        f"{'#' * section.level} {section.heading}",
                        section.heading,
                        section.heading_line,
                        "markdown.heading-v1",
                    ),
                ),
            )
            for section in unknown_sections
        )

        return ExtractedFacts(
            artifact=artifact.metadata,
            title_candidates=titles,
            summary_candidates=summaries,
            description_sections=descriptions,
            feature_facts=features,
            application_facts=applications,
            usage_sections=usage,
            identifiers=identifiers,
            manufacturer_candidates=manufacturers,
            brand_candidates=brands,
            interface_facts=interfaces,
            module_pinout=module_pinout,
            primary_ic_candidates=primary_ics,
            specifications=specifications,
            resources=resources,
            images=image_facts,
            unmapped_facts=unmapped,
            warnings=tuple(warnings),
        )

    def _titles(
        self,
        artifact: SourceArtifact,
        document: MarkdownDocument,
        h1_sections: tuple[MarkdownSection, ...],
    ) -> tuple[ExtractedField[str], ...]:
        result: list[ExtractedField[str]] = []
        for item in document.metadata_values("title"):
            result.append(
                self._field(
                    artifact,
                    item.value,
                    item.raw_text,
                    "frontmatter",
                    item.line_number,
                    "markdown.frontmatter-v1",
                    "frontmatter.title",
                )
            )
        for section in h1_sections:
            result.append(
                self._field(
                    artifact,
                    section.heading,
                    f"# {section.heading}",
                    section.heading,
                    section.heading_line,
                    "markdown.heading-v1",
                )
            )
        return self._merge_fields(result)

    def _summaries(
        self,
        artifact: SourceArtifact,
        document: MarkdownDocument,
        h1_sections: tuple[MarkdownSection, ...],
    ) -> tuple[ExtractedField[str], ...]:
        result: list[ExtractedField[str]] = []
        for item in document.metadata_values("description"):
            result.append(
                self._field(
                    artifact,
                    item.value,
                    item.raw_text,
                    "frontmatter",
                    item.line_number,
                    "markdown.frontmatter-v1",
                    "frontmatter.description",
                )
            )
        source_lines = document.preamble
        if not result and h1_sections:
            source_lines = h1_sections[0].lines
        if not result:
            for fragment in paragraphs(source_lines)[:1]:
                result.append(
                    self._field(
                        artifact,
                        fragment.value,
                        fragment.raw_text,
                        "document introduction",
                        fragment.line_number,
                        "markdown.paragraph-v1",
                    )
                )
        return self._merge_fields(result)

    def _text_sections(
        self, artifact: SourceArtifact, sections: list[MarkdownSection]
    ) -> tuple[ExtractedField[DescriptionSection], ...]:
        result: list[ExtractedField[DescriptionSection]] = []
        for section in sections:
            fragments = paragraphs(section.lines)
            if not fragments:
                fragments = list_items(section.lines)
            if not fragments:
                continue
            body = "\n\n".join(fragment.value for fragment in fragments)
            raw = "\n".join(fragment.raw_text for fragment in fragments)
            result.append(
                self._field(
                    artifact,
                    DescriptionSection(section.heading, body),
                    raw,
                    section.heading,
                    fragments[0].line_number,
                    "markdown.semantic-section-v1",
                )
            )
        return tuple(result)

    def _list_facts(
        self, artifact: SourceArtifact, sections: list[MarkdownSection]
    ) -> tuple[ExtractedField[str], ...]:
        result: list[ExtractedField[str]] = []
        for section in sections:
            fragments = list_items(section.lines) or paragraphs(section.lines)
            result.extend(
                self._field(
                    artifact,
                    fragment.value,
                    fragment.raw_text,
                    section.heading,
                    fragment.line_number,
                    "markdown.list-or-paragraph-v1",
                )
                for fragment in fragments
            )
        return tuple(result)

    def _specifications(
        self, artifact: SourceArtifact, sections: tuple[MarkdownSection, ...]
    ) -> tuple[ExtractedField[RawSpecification], ...]:
        return tuple(
            self._field(
                artifact,
                RawSpecification(fragment.label, fragment.value),
                fragment.raw_text,
                section.heading,
                fragment.line_number,
                "markdown.key-value-v1",
            )
            for section in sections
            for fragment in key_values(section.lines)
        )

    def _module_pinout(
        self, artifact: SourceArtifact, sections: list[MarkdownSection]
    ) -> tuple[ExtractedField[ModulePin], ...]:
        result: list[ExtractedField[ModulePin]] = []
        for section in sections:
            previous_count = len(result)
            rows = table_rows(section.lines)
            header: tuple[str, ...] = ()
            if rows and any(
                self._label(cell) in {"pin", "number", "name", "function", "description"}
                for cell in rows[0].cells
            ):
                header = tuple(self._label(cell) for cell in rows[0].cells)
                rows = rows[1:]
            for row in rows:
                pin = self._pin(row.cells, header)
                if pin is None:
                    continue
                result.append(
                    self._field(
                        artifact,
                        pin,
                        row.raw_text,
                        section.heading,
                        row.line_number,
                        "markdown.pin-table-v1",
                    )
                )
            if len(result) > previous_count:
                continue
            for fragment in key_values(section.lines):
                result.append(
                    self._field(
                        artifact,
                        ModulePin(number=None, name=fragment.label, function=fragment.value),
                        fragment.raw_text,
                        section.heading,
                        fragment.line_number,
                        "markdown.pin-key-value-v1",
                    )
                )
        return tuple(result)

    def _pin(self, cells: tuple[str, ...], header: tuple[str, ...]) -> ModulePin | None:
        if len(cells) < 2:
            return None
        if header:
            number = self._cell(cells, header, ("number", "pin number"))
            if number is None and "pin" in header and "name" in header:
                number = cells[header.index("pin")]
            name = self._cell(cells, header, ("name", "signal"))
            if name is None and number is None:
                name = self._cell(cells, header, ("pin",))
            function = self._cell(cells, header, ("function", "description"))
            if function is None:
                function = cells[-1]
            return ModulePin(number=number, name=name, function=function)
        first, second = cells[0], cells[1]
        if _NUMBERED_PIN.fullmatch(first):
            return ModulePin(number=first, name=None, function=second)
        return ModulePin(number=None, name=first, function=second)

    @staticmethod
    def _cell(
        cells: tuple[str, ...], header: tuple[str, ...], candidates: tuple[str, ...]
    ) -> str | None:
        index = next((header.index(value) for value in candidates if value in header), None)
        return cells[index] if index is not None and index < len(cells) and cells[index] else None

    def _resources(
        self, artifact: SourceArtifact, sections: list[MarkdownSection]
    ) -> tuple[ExtractedField[ResourceReference], ...]:
        return tuple(
            self._field(
                artifact,
                ResourceReference(
                    label=fragment.label,
                    locator=fragment.locator,
                    kind=self._resource_kind(fragment.label, fragment.locator),
                ),
                fragment.raw_text,
                section.heading,
                fragment.line_number,
                "markdown.link-v1",
            )
            for section in sections
            for fragment in links(section.lines)
        )

    def _images(
        self, artifact: SourceArtifact, document: MarkdownDocument
    ) -> tuple[ExtractedField[ImageReference], ...]:
        return tuple(
            self._field(
                artifact,
                ImageReference(fragment.locator, fragment.alt_text),
                fragment.raw_text,
                self._section_at(document, fragment.line_number),
                fragment.line_number,
                "markdown.image-v1",
            )
            for fragment in images(document.all_lines())
        )

    def _identifiers(
        self,
        artifact: SourceArtifact,
        document: MarkdownDocument,
        values: tuple[tuple[MarkdownSection, KeyValueFragment], ...],
    ) -> tuple[ExtractedField[Identifier], ...]:
        result: list[ExtractedField[Identifier]] = []
        for key, kind in _IDENTIFIER_LABELS.items():
            for item in document.metadata_values(key.replace(" ", "_")):
                result.append(
                    self._field(
                        artifact,
                        Identifier(kind, item.value),
                        item.raw_text,
                        "frontmatter",
                        item.line_number,
                        "markdown.frontmatter-v1",
                        f"frontmatter.{item.key}",
                    )
                )
        for section, fragment in values:
            detected_kind = _IDENTIFIER_LABELS.get(self._label(fragment.label))
            if detected_kind is not None:
                result.append(
                    self._field(
                        artifact,
                        Identifier(detected_kind, fragment.value),
                        fragment.raw_text,
                        section.heading,
                        fragment.line_number,
                        "markdown.identity-key-value-v1",
                    )
                )
        return self._merge_fields(result)

    def _label_string_facts(
        self,
        artifact: SourceArtifact,
        values: tuple[tuple[MarkdownSection, KeyValueFragment], ...],
        labels: frozenset[str],
    ) -> tuple[ExtractedField[str], ...]:
        result: list[ExtractedField[str]] = []
        for section, fragment in values:
            if self._label(fragment.label) in labels:
                result.append(
                    self._field(
                        artifact,
                        fragment.value,
                        fragment.raw_text,
                        section.heading,
                        fragment.line_number,
                        "markdown.semantic-key-value-v1",
                    )
                )
        return self._merge_fields(result)

    def _primary_ics(
        self,
        artifact: SourceArtifact,
        document: MarkdownDocument,
        values: tuple[tuple[MarkdownSection, KeyValueFragment], ...],
    ) -> tuple[ExtractedField[Identifier], ...]:
        result: list[ExtractedField[Identifier]] = []
        for section, fragment in values:
            if self._label(fragment.label) in _PRIMARY_IC_LABELS:
                result.append(
                    self._field(
                        artifact,
                        Identifier(IdentifierKind.PART_NUMBER, fragment.value),
                        fragment.raw_text,
                        section.heading,
                        fragment.line_number,
                        "markdown.primary-ic-key-value-v1",
                    )
                )
        for section in document.sections:
            for line in section.lines:
                match = _PART_MENTION.search(clean_inline(line.text))
                if match is not None:
                    result.append(
                        self._field(
                            artifact,
                            Identifier(IdentifierKind.PART_NUMBER, match.group(1)),
                            line.text,
                            section.heading,
                            line.number,
                            "markdown.primary-ic-mention-v1",
                        )
                    )
        return self._merge_fields(result)

    def _unmapped_sections(
        self, artifact: SourceArtifact, sections: list[MarkdownSection]
    ) -> tuple[ExtractedField[UnknownFact], ...]:
        result: list[ExtractedField[UnknownFact]] = []
        for section in sections:
            raw = "\n".join(line.text for line in section.lines if line.text.strip())
            value = self._section_text(section)
            if not raw or not value:
                continue
            result.append(
                self._field(
                    artifact,
                    UnknownFact(section.heading, value),
                    raw,
                    section.heading,
                    section.lines[0].number if section.lines else section.heading_line,
                    "markdown.unmapped-section-v1",
                )
            )
        return tuple(result)

    def _field[ValueT](
        self,
        artifact: SourceArtifact,
        value: ValueT,
        raw_value: str,
        section: str,
        line_number: int,
        method: str,
        selector: str | None = None,
    ) -> ExtractedField[ValueT]:
        return ExtractedField(
            value=value,
            raw_value=raw_value,
            evidence=(self._evidence(artifact, raw_value, section, line_number, method, selector),),
        )

    @staticmethod
    def _merge_fields[ValueT](
        fields: list[ExtractedField[ValueT]],
    ) -> tuple[ExtractedField[ValueT], ...]:
        merged: list[ExtractedField[ValueT]] = []
        for field in fields:
            existing_index = next(
                (index for index, existing in enumerate(merged) if existing.value == field.value),
                None,
            )
            if existing_index is None:
                merged.append(field)
                continue
            existing = merged[existing_index]
            merged[existing_index] = ExtractedField(
                value=existing.value,
                raw_value=existing.raw_value,
                evidence=tuple(dict.fromkeys((*existing.evidence, *field.evidence))),
            )
        return tuple(merged)

    def _evidence(
        self,
        artifact: SourceArtifact,
        raw_text: str,
        section: str,
        line_number: int,
        method: str,
        selector: str | None = None,
    ) -> EvidenceFragment:
        return EvidenceFragment(
            source=artifact.metadata.source,
            selector=selector or f"line[{line_number}]",
            section=section,
            raw_text=raw_text,
            extraction_method=method,
            parser_version=self.parser_version,
        )

    @staticmethod
    def _section_kind(heading: str) -> str | None:
        normalized = _HEADING_TOKEN.sub(" ", heading.casefold()).strip()
        return next(
            (kind for kind, aliases in _SECTION_ALIASES.items() if normalized in aliases), None
        )

    @staticmethod
    def _label(value: str) -> str:
        return _LABEL_TOKEN.sub(" ", value.casefold()).strip()

    @staticmethod
    def _section_text(section: MarkdownSection) -> str:
        values = [clean_inline(line.text) for line in section.lines if line.text.strip()]
        return " ".join(value for value in values if value)

    @staticmethod
    def _section_at(document: MarkdownDocument, line_number: int) -> str:
        candidates = [
            section for section in document.sections if section.heading_line <= line_number
        ]
        return candidates[-1].heading if candidates else "document"

    @staticmethod
    def _resource_kind(label: str, locator: str) -> ResourceKind:
        value = f"{label} {locator}".casefold()
        for token, kind in (
            ("datasheet", ResourceKind.DATASHEET),
            ("library", ResourceKind.LIBRARY),
            ("schematic", ResourceKind.SCHEMATIC),
            ("example", ResourceKind.EXAMPLE),
            ("document", ResourceKind.DOCUMENTATION),
        ):
            if token in value:
                return kind
        return ResourceKind.OTHER

    @staticmethod
    def _warning_message(code: str) -> str:
        return {
            "frontmatter_unterminated": "Frontmatter has no closing delimiter.",
            "frontmatter_entry_ignored": "A malformed frontmatter entry was ignored.",
            "frontmatter_value_ignored": "An unsafe or empty frontmatter value was ignored.",
            "executable_construct_ignored": "Executable Markdown or MDX content was ignored.",
        }.get(code, "The source contained an extraction warning.")
