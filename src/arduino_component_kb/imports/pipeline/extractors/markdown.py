"""Non-executing Markdown/MDX syntax primitives with source line retention."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_KEY_VALUE = re.compile(r"^[-*]?\s*\*{0,2}([^:*|]{2,100})\*{0,2}\s*:\s*(.{1,2000})$")
_LIST_ITEM = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_JSX_TAG = re.compile(r"<[/!]?[A-Za-z][^>]*>")
_JSX_EXPRESSION = re.compile(r"\{[^{}]{0,2000}\}")
_STRONG_ASTERISK = re.compile(r"\*\*([^*]+)\*\*")
_EMPHASIS_ASTERISK = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_STRONG_UNDERSCORE = re.compile(r"(?<!\w)__([^_]+)__(?!\w)")
_EMPHASIS_UNDERSCORE = re.compile(r"(?<!\w)_([^_]+)_(?!\w)")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class SourceLine:
    number: int
    text: str


@dataclass(frozen=True, slots=True)
class MetadataField:
    key: str
    value: str
    raw_text: str
    line_number: int


@dataclass(frozen=True, slots=True)
class MarkdownSection:
    heading: str
    level: int
    heading_line: int
    lines: tuple[SourceLine, ...]


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    metadata: tuple[MetadataField, ...]
    preamble: tuple[SourceLine, ...]
    sections: tuple[MarkdownSection, ...]
    warnings: tuple[str, ...]

    def metadata_values(self, key: str) -> tuple[MetadataField, ...]:
        normalized = key.casefold()
        return tuple(item for item in self.metadata if item.key == normalized)

    def all_lines(self) -> tuple[SourceLine, ...]:
        section_lines = tuple(line for section in self.sections for line in section.lines)
        return (*self.preamble, *section_lines)


@dataclass(frozen=True, slots=True)
class TextFragment:
    value: str
    raw_text: str
    line_number: int


@dataclass(frozen=True, slots=True)
class KeyValueFragment:
    label: str
    value: str
    raw_text: str
    line_number: int


@dataclass(frozen=True, slots=True)
class TableFragment:
    cells: tuple[str, ...]
    raw_text: str
    line_number: int


@dataclass(frozen=True, slots=True)
class LinkFragment:
    label: str
    locator: str
    raw_text: str
    line_number: int


@dataclass(frozen=True, slots=True)
class ImageFragment:
    alt_text: str | None
    locator: str
    raw_text: str
    line_number: int


def parse_markdown(content: bytes) -> MarkdownDocument:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("markdown_not_utf8") from error
    raw_lines = text.splitlines()
    metadata, body_start, warnings = _frontmatter(raw_lines)
    safe_lines, executable_warning = _safe_lines(raw_lines[body_start:], body_start + 1)
    if executable_warning:
        warnings.append("executable_construct_ignored")

    sections: list[MarkdownSection] = []
    preamble: list[SourceLine] = []
    heading: str | None = None
    level = 0
    heading_line = 1
    current: list[SourceLine] = []
    for line in safe_lines:
        match = _HEADING.match(line.text.strip())
        if match is None:
            current.append(line)
            continue
        if heading is None:
            preamble.extend(current)
        else:
            sections.append(MarkdownSection(heading, level, heading_line, tuple(current)))
        heading = clean_inline(match.group(2))
        level = len(match.group(1))
        heading_line = line.number
        current = []
    if heading is None:
        preamble.extend(current)
    else:
        sections.append(MarkdownSection(heading, level, heading_line, tuple(current)))
    return MarkdownDocument(
        metadata=tuple(metadata),
        preamble=tuple(preamble),
        sections=tuple(sections),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def clean_inline(value: str) -> str:
    cleaned = _IMAGE.sub("", value)
    cleaned = _LINK.sub(lambda match: match.group(1), cleaned)
    cleaned = _JSX_TAG.sub("", cleaned)
    cleaned = _JSX_EXPRESSION.sub("", cleaned)
    cleaned = _STRONG_ASTERISK.sub(r"\1", cleaned)
    cleaned = _EMPHASIS_ASTERISK.sub(r"\1", cleaned)
    cleaned = _STRONG_UNDERSCORE.sub(r"\1", cleaned)
    cleaned = _EMPHASIS_UNDERSCORE.sub(r"\1", cleaned)
    cleaned = re.sub(r"[`~]", "", cleaned)
    return _SPACE.sub(" ", cleaned).strip()


def paragraphs(lines: tuple[SourceLine, ...]) -> tuple[TextFragment, ...]:
    fragments: list[TextFragment] = []
    collected: list[SourceLine] = []

    def flush() -> None:
        if not collected:
            return
        raw = "\n".join(line.text for line in collected)
        value = clean_inline(" ".join(line.text for line in collected))
        if value:
            fragments.append(TextFragment(value, raw, collected[0].number))
        collected.clear()

    for line in lines:
        stripped = line.text.strip()
        if (
            not stripped
            or stripped.startswith("|")
            or _LIST_ITEM.match(stripped)
            or _IMAGE.search(stripped)
        ):
            flush()
            continue
        collected.append(line)
    flush()
    return tuple(fragments)


def list_items(lines: tuple[SourceLine, ...]) -> tuple[TextFragment, ...]:
    values: list[TextFragment] = []
    for line in lines:
        match = _LIST_ITEM.match(line.text)
        if match is None:
            continue
        value = clean_inline(match.group(1))
        if value:
            values.append(TextFragment(value, line.text, line.number))
    return tuple(values)


def key_values(lines: tuple[SourceLine, ...]) -> tuple[KeyValueFragment, ...]:
    values: list[KeyValueFragment] = []
    for line in lines:
        stripped = line.text.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            continue
        match = _KEY_VALUE.match(stripped)
        if match is not None:
            label = clean_inline(match.group(1))
            value = clean_inline(match.group(2))
            if label and value:
                values.append(KeyValueFragment(label, value, line.text, line.number))
    table = table_rows(lines)
    if table:
        header_tokens = {"parameter", "property", "specification", "item", "pin", "name"}
        start = 1 if any(cell.casefold() in header_tokens for cell in table[0].cells) else 0
        for row in table[start:]:
            if len(row.cells) >= 2 and row.cells[0] and row.cells[1]:
                values.append(
                    KeyValueFragment(row.cells[0], row.cells[1], row.raw_text, row.line_number)
                )
    return tuple(values)


def table_rows(lines: tuple[SourceLine, ...]) -> tuple[TableFragment, ...]:
    rows: list[TableFragment] = []
    for line in lines:
        stripped = line.text.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = tuple(clean_inline(cell) for cell in stripped.strip("|").split("|"))
        if cells and not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            rows.append(TableFragment(cells, line.text, line.number))
    return tuple(rows)


def links(lines: tuple[SourceLine, ...]) -> tuple[LinkFragment, ...]:
    return tuple(
        LinkFragment(clean_inline(match.group(1)), match.group(2), line.text, line.number)
        for line in lines
        for match in _LINK.finditer(line.text)
    )


def images(lines: tuple[SourceLine, ...]) -> tuple[ImageFragment, ...]:
    return tuple(
        ImageFragment(clean_inline(match.group(1)) or None, match.group(2), line.text, line.number)
        for line in lines
        for match in _IMAGE.finditer(line.text)
    )


def _frontmatter(lines: list[str]) -> tuple[list[MetadataField], int, list[str]]:
    if not lines or lines[0].strip() != "---":
        return [], 0, []
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return [], 0, ["frontmatter_unterminated"]
    metadata: list[MetadataField] = []
    warnings: list[str] = []
    for index, raw in enumerate(lines[1:end], start=2):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            warnings.append("frontmatter_entry_ignored")
            continue
        key, raw_value = raw.split(":", 1)
        key = key.strip().casefold()
        value = raw_value.strip().strip("'\"")
        if (
            re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", key) is None
            or not value
            or any(token in value for token in ("!!", "&", "*"))
        ):
            warnings.append("frontmatter_value_ignored")
            continue
        metadata.append(MetadataField(key, clean_inline(value), raw, index))
    return metadata, end + 1, warnings


def _safe_lines(lines: list[str], first_line: int) -> tuple[list[SourceLine], bool]:
    safe: list[SourceLine] = []
    fenced = False
    ignored = False
    for offset, raw in enumerate(lines):
        line_number = first_line + offset
        stripped = raw.lstrip()
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
            ignored = True
            continue
        if fenced or stripped.startswith(("import ", "export ")):
            ignored = True
            continue
        if _JSX_TAG.search(raw) or _JSX_EXPRESSION.search(raw):
            ignored = True
        cleaned = _JSX_EXPRESSION.sub("", _JSX_TAG.sub("", raw))
        safe.append(SourceLine(line_number, cleaned))
    return safe, ignored
