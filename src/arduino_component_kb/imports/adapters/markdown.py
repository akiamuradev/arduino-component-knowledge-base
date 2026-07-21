"""Non-executing Markdown/MDX primitives for the Seeed adapter."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_KEY_VALUE = re.compile(r"^[-*]?\s*\*{0,2}([^:*|]{2,80})\*{0,2}\s*:\s*(.{1,300})$")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_JSX_TAG = re.compile(r"<[/!]?[A-Za-z][^>]*>")
_JSX_EXPR = re.compile(r"\{[^{}]{0,1000}\}")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class MarkdownSection:
    heading: str
    lines: tuple[str, ...]
    line_number: int


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    metadata: dict[str, str]
    sections: tuple[MarkdownSection, ...]
    preamble: tuple[str, ...]
    warnings: tuple[str, ...]


def load_markdown(content: bytes) -> MarkdownDocument:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("markdown_not_utf8") from error
    metadata, body, warnings = _frontmatter(text)
    safe_lines = _without_executable_constructs(body.splitlines())
    sections: list[MarkdownSection] = []
    preamble: list[str] = []
    heading: str | None = None
    heading_line = 1
    current: list[str] = []
    for number, line in safe_lines:
        match = _HEADING.match(line.strip())
        if match:
            if heading is None:
                preamble.extend(current)
            else:
                sections.append(MarkdownSection(heading, tuple(current), heading_line))
            heading = clean_text(match.group(2))
            heading_line = number
            current = []
        else:
            current.append(line)
    if heading is None:
        preamble.extend(current)
    else:
        sections.append(MarkdownSection(heading, tuple(current), heading_line))
    return MarkdownDocument(metadata, tuple(sections), tuple(preamble), tuple(warnings))


def clean_text(value: str) -> str:
    value = _LINK.sub(lambda match: match.group(1), value)
    value = re.sub(r"(?<=\d)\s*[~～]\s*(?=[+-]?\d)", "–", value)
    value = re.sub(r"[*_`~]", "", value)
    return _SPACE.sub(" ", value).strip()


def paragraph(lines: tuple[str, ...]) -> str | None:
    collected: list[str] = []
    for line in lines:
        stripped = clean_text(line)
        if not stripped:
            if collected:
                break
            continue
        if stripped.startswith(("|", "- ", "* ", "! [", "![")):
            if collected:
                break
            continue
        collected.append(stripped)
    value = clean_text(" ".join(collected))
    return value or None


def key_values(lines: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    table: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [clean_text(cell) for cell in stripped.strip("|").split("|")]
            if cells and not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                table.append(cells)
            continue
        match = _KEY_VALUE.match(stripped)
        if match:
            result.append((clean_text(match.group(1)), clean_text(match.group(2))))
    if len(table) >= 2:
        header_names = {"parameter", "property", "specification", "item", "pin", "name"}
        start = 1 if any(value.casefold() in header_names for value in table[0]) else 0
        for row in table[start:]:
            if len(row) >= 2 and row[0] and row[1]:
                result.append((row[0], row[1]))
    return tuple(dict.fromkeys(result))


def links(lines: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple((clean_text(label), url) for line in lines for label, url in _LINK.findall(line))


def normalize_unit(value: str) -> str:
    replacements = {
        "microampere": "µA",
        "microamps": "µA",
        "milliamps": "mA",
        "millivolts": "mV",
        "millimeters": "mm",
        "centimeters": "cm",
        "grams": "g",
        "volts": "V",
        "volt": "V",
        "kilohms": "kΩ",
        "kohm": "kΩ",
        "degrees celsius": "°C",
        "degree celsius": "°C",
        "degree c": "°C",
    }
    normalized = clean_text(value).replace("μ", "µ")
    for source, target in replacements.items():
        normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"(?<=\d)\s*-\s*(?=\d)", "–", normalized)
    normalized = re.sub(
        r"(?<=\d)(?=(?:°C|µA|mA|mV|kΩ|kHz|MHz|Hz|cm|mm|V|A|g)(?:\b|$))",
        " ",
        normalized,
    )
    normalized = re.sub(r"\s+[xX]\s+", " × ", normalized)
    return normalized


def _frontmatter(text: str) -> tuple[dict[str, str], str, list[str]]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text, []
    lines = text.splitlines()
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        return {}, text, ["frontmatter_unterminated"]
    metadata: dict[str, str] = {}
    warnings: list[str] = []
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            warnings.append("frontmatter_entry_ignored")
            continue
        key, value = line.split(":", 1)
        key = key.strip().casefold()
        value = value.strip().strip("'\"")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", key) or any(
            token in value for token in ("!!", "&", "*")
        ):
            warnings.append("frontmatter_unsafe_value_ignored")
            continue
        metadata[key] = clean_text(value)[:500]
    return metadata, "\n".join(lines[end + 1 :]), warnings


def _without_executable_constructs(lines: list[str]) -> list[tuple[int, str]]:
    safe: list[tuple[int, str]] = []
    fenced = False
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```") or line.lstrip().startswith("~~~"):
            fenced = not fenced
            continue
        if fenced or line.lstrip().startswith(("import ", "export ")):
            continue
        line = _JSX_TAG.sub("", line)
        line = _JSX_EXPR.sub("", line)
        if line.lstrip().startswith("!") and "[" in line:
            continue
        safe.append((number, line))
    return safe
