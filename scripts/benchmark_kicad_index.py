"""Measure cold/cached KiCad indexing and deterministic lookup latency."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from arduino_component_kb.imports.pipeline.enrichment import KicadSymbolIndexer
from arduino_component_kb.imports.repository_domain import RepositorySnapshot

REPOSITORY_URL = "https://gitlab.com/kicad/libraries/kicad-symbols"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("--revision", default="a" * 40)
    parser.add_argument("--query", default="SSD1306")
    parser.add_argument("--iterations", type=int, default=10_000)
    arguments = parser.parse_args()
    if not 1 <= arguments.iterations <= 1_000_000:
        raise SystemExit("iterations must be between 1 and 1000000")
    files = {
        path.relative_to(arguments.snapshot_dir).as_posix(): path.read_bytes()
        for path in arguments.snapshot_dir.rglob("*.kicad_sym")
    }
    snapshot = RepositorySnapshot(REPOSITORY_URL, arguments.revision, files)
    indexer = KicadSymbolIndexer()
    cold = indexer.build(snapshot)
    cached = indexer.build(snapshot)
    started = perf_counter()
    for _ in range(arguments.iterations):
        cold.index.exact_part_number(arguments.query)
    lookup_ms = (perf_counter() - started) * 1_000
    print(
        json.dumps(
            {
                "files": len(files),
                "symbols": len(cold.index.records),
                "cold_build_ms": round(cold.stats.duration_ms, 3),
                "cached_build_ms": round(cached.stats.duration_ms, 3),
                "lookup_query": arguments.query,
                "lookup_iterations": arguments.iterations,
                "lookup_total_ms": round(lookup_ms, 3),
                "lookup_mean_us": round(lookup_ms * 1_000 / arguments.iterations, 3),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
