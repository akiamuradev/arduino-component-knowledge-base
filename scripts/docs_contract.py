"""Validate cross-document contracts for the requirements-only project stage."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    ROOT / "docs" / "REQUIREMENTS.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "DATA_MODEL.md",
    ROOT / "docs" / "SECURITY.md",
)
URLS = (
    "https://arduino-tex.ru/",
    "https://portal-pk.ru/",
    "https://alexgyver.ru/ardu-proj/",
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
            errors.append(f"REQUIREMENTS.md does not contain approved URL {url}")

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
