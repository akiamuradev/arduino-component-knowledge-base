# KiCad enrichment index

Status: stage 6 implementation, provider `kicad-symbol-enrichment-v1`, index parser
`kicad-index-v1.0.0`.

KiCad is now modelled as an enrichment source for a resolved Seeed identity. The new path emits
`KicadCandidateSet`; it does not compose a catalogue card and does not access persistence.
Relation type, calibrated confidence and final acceptance remain the responsibility of stage 7.

## Index contract

`KicadSymbolIndexer` accepts only an immutable snapshot of the official KiCad symbols repository
and allowlisted `.kicad_sym` libraries. One bounded S-expression pass creates immutable
`KicadSymbolRecord` values with:

- library and symbol identity, aliases and normalized names;
- description, keywords, manufacturer hints and datasheet;
- pins with unit and electrical type, plus footprint filters;
- source path, commit, content hash and parser version.

Lookup maps support exact part numbers, aliases, normalized names, description tokens and
manufacturer hints. A provider lookup reuses those maps and never rescans the snapshot.

The in-process cache keys each library by its content SHA-256. An identical snapshot is an exact
cache hit. On a new revision only changed files are parsed; unchanged records are reused with the
new revision, and removed files disappear from the rebuilt index. Parse warnings are stable across
an exact cache hit.

## Candidate safety policy

`KiCadEnrichmentProvider.find_candidates(identity, facts)` returns evidence about matching bases,
not a score. Manufacturer is only allowed to annotate an existing identity/name match; it cannot
introduce a candidate by itself. Generic resistor, capacitor, inductor, LED and connector symbols
are filtered unless an evidenced part-number or primary-IC term exactly names that symbol.

The old `KicadSymbolsAdapter` card workflow is deprecated but defaults on for rollback
compatibility. Set `ACKB_LEGACY_KICAD_CARD_IMPORT_ENABLED=false` to reject new legacy KiCad card
previews/jobs while leaving Seeed imports and the enrichment index available.

## Benchmark

Run the bounded local benchmark against a checked-out symbol snapshot:

```bash
uv run python scripts/benchmark_kicad_index.py /path/to/kicad-symbols \
  --revision <40-character-commit> --query SSD1306 --iterations 10000
```

The command reports cold build time, exact-cache rebuild time and mean exact lookup latency as
JSON. The committed fixture baseline is intentionally small and is recorded by the stage tests;
production capacity checks should use the exact pinned KiCad revision intended for deployment.

On 2026-07-23 the committed 11-file/10-symbol fixture snapshot produced a 1.518 ms cold build,
0.065 ms exact-cache rebuild and 0.341 microsecond mean exact lookup over 10,000 iterations. These
numbers are a regression smoke baseline, not a production-capacity estimate.

## Verification

`tests/test_kicad_enrichment.py` covers record extraction, all search maps, stable warnings, exact
cache hits, per-file invalidation, removal, generic filtering, provider orchestration, immutable
JSON round trips and the absence of a card payload.
