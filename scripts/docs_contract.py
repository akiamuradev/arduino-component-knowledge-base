"""Validate cross-document and public Markdown contracts."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    ROOT / "docs" / "REQUIREMENTS.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "DATA_MODEL.md",
    ROOT / "docs" / "SECURITY.md",
)
PUBLIC_MARKDOWN = (
    ROOT / "README.md",
    ROOT / "README.ru.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "CHANGELOG.md",
    ROOT / "THIRD_PARTY_NOTICES.md",
    ROOT / "frontend" / "README.md",
    *sorted((ROOT / "docs").rglob("*.md")),
)
URLS = (
    "https://github.com/Seeed-Studio/wiki-documents",
    "https://gitlab.com/kicad/libraries/kicad-symbols",
)
REQUIRED_CONTRACTS = {
    "React + TypeScript": ("REQUIREMENTS.md", "ARCHITECTURE.md"),
    "FastAPI": ("REQUIREMENTS.md", "ARCHITECTURE.md"),
    "PostgreSQL": ("REQUIREMENTS.md", "ARCHITECTURE.md", "DATA_MODEL.md"),
    "MinIO": ("REQUIREMENTS.md", "ARCHITECTURE.md", "DATA_MODEL.md", "SECURITY.md"),
    "Redis": ("REQUIREMENTS.md", "ARCHITECTURE.md", "SECURITY.md"),
    "Dramatiq": ("REQUIREMENTS.md", "ARCHITECTURE.md", "SECURITY.md"),
    "Alembic": ("REQUIREMENTS.md", "ARCHITECTURE.md", "DATA_MODEL.md", "SECURITY.md"),
    "draft": ("REQUIREMENTS.md", "ARCHITECTURE.md", "DATA_MODEL.md", "SECURITY.md"),
    "administrator": ("REQUIREMENTS.md", "ARCHITECTURE.md", "DATA_MODEL.md", "SECURITY.md"),
}


def read_documents() -> dict[str, str]:
    """Read all required documents and return them by file name."""
    missing = [str(path.relative_to(ROOT)) for path in DOCS if not path.is_file()]
    if missing:
        raise AssertionError(f"Missing required documents: {', '.join(missing)}")
    return {path.name: path.read_text(encoding="utf-8") for path in DOCS}


def heading_anchors(content: str) -> set[str]:
    """Return GitHub-style anchors, including duplicate-heading suffixes."""
    anchors: set[str] = set(re.findall(r'<a\s+(?:id|name)="([^"]+)"', content, re.IGNORECASE))
    occurrences: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*$", content, re.MULTILINE):
        plain = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", heading)
        plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
        plain = re.sub(r"[`*_~]", "", plain).casefold()
        slug = "".join(
            character for character in plain if character.isalnum() or character in " -_"
        )
        slug = re.sub(r"\s+", "-", slug.strip())
        slug = re.sub(r"-+", "-", slug)
        suffix = occurrences.get(slug, 0)
        occurrences[slug] = suffix + 1
        anchors.add(slug if suffix == 0 else f"{slug}-{suffix}")
    return anchors


def validate_markdown_links() -> list[str]:
    """Validate local inline Markdown targets and their heading fragments."""
    errors: list[str] = []
    missing = [path.relative_to(ROOT).as_posix() for path in PUBLIC_MARKDOWN if not path.is_file()]
    if missing:
        return [f"Missing public Markdown file: {path}" for path in missing]

    link_pattern = re.compile(r"!?\[[^\]]*]\(([^)\n]+)\)")
    anchor_cache: dict[Path, set[str]] = {}
    for source in PUBLIC_MARKDOWN:
        content = source.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(content):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            raw_path, separator, raw_fragment = target.partition("#")
            decoded_path = unquote(raw_path)
            destination = source if not decoded_path else (source.parent / decoded_path).resolve()
            if not destination.exists():
                errors.append(
                    f"{source.relative_to(ROOT)} links to missing local target {raw_path!r}"
                )
                continue
            if separator and destination.is_file() and destination.suffix.casefold() == ".md":
                fragment = unquote(raw_fragment).casefold()
                anchors = anchor_cache.setdefault(
                    destination,
                    heading_anchors(destination.read_text(encoding="utf-8")),
                )
                if fragment not in anchors:
                    errors.append(
                        f"{source.relative_to(ROOT)} links to missing anchor "
                        f"{raw_fragment!r} in {destination.relative_to(ROOT)}"
                    )
    return errors


def validate() -> list[str]:
    """Return human-readable contract violations."""
    errors: list[str] = []
    try:
        documents = read_documents()
    except AssertionError as error:
        return [str(error)]

    requirements = documents["REQUIREMENTS.md"]
    for url in URLS:
        if url not in requirements:
            errors.append(f"REQUIREMENTS.md does not contain registered repository {url}")

    for token in ("owner_denied_usage", "permission_status=denied", "GPL-3.0-only", "CC-BY-SA-4.0"):
        if token not in requirements:
            errors.append(f"REQUIREMENTS.md does not contain source policy {token!r}")

    for token, names in REQUIRED_CONTRACTS.items():
        for name in names:
            if token.casefold() not in documents[name].casefold():
                errors.append(f"{name} does not contain required contract {token!r}")

    for name, content in documents.items():
        if not content.startswith("# "):
            errors.append(f"{name} must start with one H1 heading")
        if "\t" in content:
            errors.append(f"{name} contains a tab character")
        trailing = [
            index
            for index, line in enumerate(content.splitlines(), start=1)
            if line.rstrip() != line
        ]
        if trailing:
            errors.append(f"{name} has trailing whitespace on lines {trailing}")

    if "Только administrator" not in requirements:
        errors.append("REQUIREMENTS.md must reserve duplicate merge for administrator")
    if "backend" not in requirements.casefold() or "источник" not in requirements.casefold():
        errors.append("REQUIREMENTS.md must state backend authorization authority")
    errors.extend(validate_markdown_links())
    return errors


def main() -> int:
    """Run the smoke validation and return a process exit code."""
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Documentation contract smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
