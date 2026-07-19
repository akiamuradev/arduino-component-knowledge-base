"""CLI dry-run for one file from an already acquired immutable snapshot."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from arduino_component_kb.imports.adapters.kicad_symbols import (
    DEFAULT_LIBRARY_ALLOWLIST,
    KicadSymbolsAdapter,
)
from arduino_component_kb.imports.adapters.repository import RepositorySourceAdapter
from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.repository_domain import RepositoryEntry, RepositorySnapshot


def _safe_file(root: Path, relative: str) -> tuple[str, bytes]:
    root = root.resolve(strict=True)
    if root.is_symlink():
        raise ValueError("repository_root_symlink_forbidden")
    candidate = root.joinpath(relative)
    if candidate.is_symlink():
        raise ValueError("repository_file_symlink_forbidden")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("repository_file_outside_root")
    content = resolved.read_bytes()
    return resolved.relative_to(root).as_posix(), content


async def dry_run(args: argparse.Namespace) -> dict[str, object]:
    path, content = _safe_file(args.repository_root, args.file)
    if args.source == "seeed":
        adapter: RepositorySourceAdapter = SeeedWikiAdapter()
    else:
        configured = os.environ.get("ACKB_KICAD_LIBRARY_ALLOWLIST")
        prefixes = (
            tuple(part.strip() for part in configured.split(",") if part.strip())
            if configured
            else DEFAULT_LIBRARY_ALLOWLIST
        )
        adapter = KicadSymbolsAdapter(prefixes)
    snapshot = RepositorySnapshot(adapter.repository_url, args.revision, {path: content})
    result = await adapter.parse_entry(
        snapshot,
        RepositoryEntry(path, entry_name=args.entry),
        parsed_at=datetime.now(UTC),
        source_tag=args.tag,
    )
    return result.as_dict()


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Parse one local file at a caller-verified immutable repository revision."
    )
    command.add_argument("--source", choices=("seeed", "kicad"), required=True)
    command.add_argument("--repository-root", type=Path, required=True)
    command.add_argument("--revision", required=True, help="Full 40-character commit SHA")
    command.add_argument("--file", required=True, help="POSIX path relative to repository root")
    command.add_argument("--entry", help="KiCad symbol name")
    command.add_argument("--tag", help="Optional human-readable tag resolved to --revision")
    return command


def main() -> None:
    args = parser().parse_args()
    if args.source == "kicad" and not args.entry:
        raise SystemExit("--entry is required for kicad")
    try:
        result = asyncio.run(dry_run(args))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
