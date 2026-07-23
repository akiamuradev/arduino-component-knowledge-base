# Import pipeline persistence and enrichment lifecycle

Stage 10 adds a PostgreSQL adapter for the evidence-first pipeline. It remains parallel to the
release `0.21.0` import path. Stage 11 may write it in optional shadow mode and Stage 12 reads it
through an administrator-only review API, but neither stage makes it authoritative or publishes a
catalogue card. The adapter stores immutable source-derived snapshots and keeps KiCad lifecycle
changes separate from the Seeed review draft and catalogue card.

## Records

| Table | Purpose | Mutability |
| --- | --- | --- |
| `import_pipeline_artifacts` | Source location/revision, content and normalized-facts snapshots | Immutable except nullable `component_id` attachment |
| `component_identity_candidates` | Explainable identity/category candidate payload | Immutable |
| `parser_evaluations` | Versioned quality report, score and route | Immutable |
| `import_review_drafts` | Deterministic Stage 9 review draft | Immutable except nullable `component_id` attachment |
| `component_enrichments` | KiCad candidate, evidence and current lifecycle state | Payload immutable; lifecycle/reviewer fields mutable |
| `component_enrichment_reviews` | Append-only human accept/reject audit | Immutable |
| `import_review_states` | Stage 12 selected identity, spec mappings, parser issues and confirmation | Versioned mutable state |
| `import_review_actions` | Stage 12 reviewer decision history | Immutable |

The normalization registry remains code-versioned. Each artifact records
`normalization_version=SpecificationRegistry.version`, while the normalized payload preserves each
rule trace and unmapped source label. A mutable `specification_aliases` table is deliberately not
introduced before the admin review API exists; changing aliases means shipping a new registry
version and recalculating from the immutable facts snapshot.

## Idempotency

Artifact, identity, evaluation, draft and enrichment IDs are UUIDv5 values derived from their source
revision, content/payload digest and external KiCad identity. Every insert uses PostgreSQL
`ON CONFLICT DO NOTHING`. Retrying the same pipeline input therefore returns the same IDs and does
not create duplicate rows. A new source or KiCad revision creates a new immutable set instead of
overwriting old evidence.

The gateway flushes but does not commit. The caller owns the transaction, so a failed stage cannot
leave a partial aggregate.

## KiCad lifecycle

Statuses are `suggested`, `accepted`, `rejected`, `stale` and `conflict`.

- Matcher `auto_accepted` becomes `accepted`; `review_required` becomes `suggested`; rejected
  candidates are also retained as `rejected` for evaluation and diagnostics.
- When the KiCad index revision changes, `mark_stale()` updates only `component_enrichments` from an
  older revision. It never updates `components`, draft JSON or source/facts JSON.
- Recalculation runs enrichment against the new index and persists a new revision-bound row. The old
  row remains stale and auditable.
- Human accept/reject locks the row, updates reviewer metadata and appends an immutable
  `component_enrichment_reviews` record in the same transaction.
- Stale rows cannot be reviewed; they must first be recalculated. A detected ambiguity can be marked
  `conflict` and routed back to a reviewer.

Attaching an aggregate to a catalogue component updates only the nullable foreign keys. It does not
copy KiCad payload into the primary Seeed card and does not rewrite any snapshot JSON.

## Migration and rollback

Upgrade:

```bash
alembic upgrade 20260723_17
```

Rollback of Stage 10 after first removing Stage 12:

```bash
alembic downgrade 20260723_17
alembic downgrade 20260721_16
```

The downgrade drops only the six new parallel tables in dependency order. It does not alter or
delete `components`, `component_sources`, `sources`, `import_jobs` or any legacy field. Before
rollback after real pipeline traffic begins, export the new tables if their audit history must be
retained. Once a later stage wires production reads/writes to this schema, rollback also requires
disabling that wiring first.

## Verification

```bash
pytest -q tests/test_pipeline_persistence.py tests/test_migrations.py
alembic upgrade head --sql
```

The tests cover deterministic repeated persistence, all matcher decision records, source mismatch
and stage ordering, stale revision handling, append-only reviewer audit, snapshot-safe component
attachment, ORM constraints, migration rendering and downgrade isolation.
