"""Bounded batch CLI for Stage 11 shadow comparisons against local snapshots."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid5

from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.pipeline import (
    DryRunPersistenceGateway,
    EvidenceFirstImportOrchestrator,
    KicadSymbolIndexer,
    PipelineRunRequest,
    ShadowImportRunner,
    SourceArtifact,
    SourceArtifactMetadata,
    SourceReference,
)
from arduino_component_kb.imports.repository_domain import RepositoryEntry, RepositorySnapshot

_CLI_NAMESPACE = UUID("877781f3-b418-4d7d-91eb-dd706e9ab84d")


def _safe_files(root: Path, suffixes: frozenset[str], limit: int) -> dict[str, bytes]:
    resolved_root = root.resolve(strict=True)
    if resolved_root.is_symlink() or not resolved_root.is_dir():
        raise ValueError("shadow_root_invalid")
    result: dict[str, bytes] = {}
    for candidate in sorted(resolved_root.rglob("*")):
        if candidate.is_symlink():
            raise ValueError("shadow_file_symlink_forbidden")
        if not candidate.is_file() or candidate.suffix.casefold() not in suffixes:
            continue
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(resolved_root):
            raise ValueError("shadow_file_outside_root")
        content = resolved.read_bytes()
        if len(content) > 2 * 1024 * 1024:
            raise ValueError("repository_file_too_large")
        result[resolved.relative_to(resolved_root).as_posix()] = content
        if len(result) == limit:
            break
    if not result:
        raise ValueError("shadow_fixture_set_empty")
    return result


async def batch_shadow_run(args: argparse.Namespace) -> dict[str, object]:
    seeed_files = _safe_files(
        args.seeed_root,
        frozenset({".md", ".mdx"}),
        args.limit,
    )
    kicad_files = _safe_files(
        args.kicad_root,
        frozenset({".kicad_sym"}),
        args.kicad_file_limit,
    )
    kicad_snapshot = RepositorySnapshot(
        "https://gitlab.com/kicad/libraries/kicad-symbols",
        args.kicad_revision,
        kicad_files,
    )
    build = KicadSymbolIndexer().build(kicad_snapshot)
    orchestrator = EvidenceFirstImportOrchestrator(DryRunPersistenceGateway())
    runner = ShadowImportRunner(orchestrator)
    adapter = SeeedWikiAdapter()
    reports: list[dict[str, object]] = []
    succeeded = 0
    conflict_count = 0
    for path, content in seeed_files.items():
        acquired_at = datetime.now(UTC)
        snapshot = RepositorySnapshot(adapter.repository_url, args.seeed_revision, {path: content})
        legacy = await adapter.parse_entry(
            snapshot,
            RepositoryEntry(path),
            parsed_at=acquired_at,
        )
        source = SourceReference(
            adapter.source_key,
            adapter.repository_url,
            path,
            args.seeed_revision,
        )
        artifact = SourceArtifact(
            SourceArtifactMetadata(
                source,
                "text/mdx" if path.endswith(".mdx") else "text/markdown",
                sha256(content).hexdigest(),
                len(content),
                acquired_at,
            ),
            content,
        )
        run_id = uuid5(_CLI_NAMESPACE, f"{args.seeed_revision}:{path}")
        source_id = uuid5(_CLI_NAMESPACE, adapter.source_key)
        shadow = await runner.run(
            PipelineRunRequest(run_id, source_id, artifact, build.index),
            legacy,
        )
        reports.append(shadow.comparison.as_dict())
        if shadow.comparison.pipeline_status == "succeeded":
            succeeded += 1
        conflict_count += len(shadow.comparison.conflicts)
    return {
        "schema_version": "shadow-batch-report/v1",
        "production_default_changed": False,
        "seeed_revision": args.seeed_revision,
        "kicad_revision": args.kicad_revision,
        "kicad_index": {
            "symbol_count": build.stats.symbol_count,
            "parsed_files": build.stats.parsed_files,
            "warnings": list(build.stats.warnings),
        },
        "summary": {
            "total": len(reports),
            "succeeded": succeeded,
            "failed": len(reports) - succeeded,
            "conflicts": conflict_count,
        },
        "reports": reports,
    }


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Compare old and evidence-first imports on bounded local snapshot sets."
    )
    command.add_argument("--seeed-root", type=Path, required=True)
    command.add_argument("--kicad-root", type=Path, required=True)
    command.add_argument("--seeed-revision", required=True, help="Full immutable commit SHA")
    command.add_argument("--kicad-revision", required=True, help="Full immutable commit SHA")
    command.add_argument("--limit", type=int, default=15, choices=range(1, 101))
    command.add_argument("--kicad-file-limit", type=int, default=500, choices=range(1, 1001))
    return command


def main() -> None:
    args = parser().parse_args()
    try:
        report = asyncio.run(batch_shadow_run(args))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
