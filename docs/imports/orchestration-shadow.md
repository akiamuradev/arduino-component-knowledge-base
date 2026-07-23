# Stage 11 orchestrator and shadow mode

Stage 11 assembles the complete evidence-first flow:

```text
acquisition → extraction → normalization → identity
→ enrichment → quality → composition → persistence
```

The production switch is intentionally impossible in this stage. `ACKB_IMPORT_PIPELINE_MODE`
accepts only `disabled` (default) and `shadow`. The legacy repository parser and
`persist_repository_draft()` remain the source of truth and create the catalogue draft. A shadow
run can store its separate Stage 10 aggregate, but it never publishes or replaces the legacy card.

## Runtime contract

`EvidenceFirstImportOrchestrator` accepts a correlation/import run UUID, immutable Seeed artifact,
source registry UUID and a versioned KiCad index. It returns either a complete `PipelineRunResult`
or a bounded `PipelineRunFailure` with stage, safe code, retryability, attempts, duration and error
type. Arbitrary exception messages and source payloads are not logged.

Every stage has an `asyncio.timeout`. Only acquisition and enrichment are designated safe to retry;
persistence, composition and all other stateful/deterministic stages run once. Timeouts and errors
become explicit failure outcomes rather than escaping into the legacy worker. The bridge catches any
remaining integration error and continues the old import.

Structured events include `import_run_id`, stage, attempt, outcome, safe failure code, warning count,
duration and `shadow_mode=true`. The JSON formatter allowlists these fields and discards source text
or arbitrary record extras.

## Comparison report

`ShadowComparisonReport` records:

- legacy/new field counts, coverage, missing and additional field names;
- conflicts as field name plus old/new SHA-256 only;
- quality route and score;
- parser and quality warning codes;
- KiCad candidate counts by auto-accepted/review/rejected decision;
- execution time and a typed failure when the new pipeline stops.

The current `kicad_candidate_precision_basis_points` is explicitly marked `proxy_unreviewed`. It is
the auto-accepted share of accepted/rejected matcher decisions, not human-labelled precision. True
precision requires Stage 12 reviewer outcomes and must not be inferred from this proxy.

For online worker shadow runs, the bridge currently supplies an empty, revision-marked KiCad index.
This exercises the full lifecycle without performing a second remote repository fetch in a job.
The batch command accepts a real local KiCad snapshot and is the meaningful source of matcher
comparison data until a durable index distribution service is wired.

## Batch dry-run

The command reads bounded, caller-provided local snapshot directories and performs no database
writes:

```bash
ackb-shadow-import-batch \
  --seeed-root tests/fixtures/seeed \
  --kicad-root tests/fixtures/kicad \
  --seeed-revision aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --kicad-revision bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
  --limit 15
```

Symlinks, files outside the roots, oversized files and empty fixture sets are rejected. Output is a
versioned JSON summary plus per-source comparison reports.

## Recorded fixture shadow run

Stage 11 was evaluated against all 15 versioned Seeed fixtures and the 10-symbol KiCad fixture
index:

| Metric | Result |
| --- | ---: |
| Total Seeed entries | 15 |
| Complete pipeline successes | 14 |
| Expected quality/composition rejection | 1 |
| Field conflicts (hashed) | 18 |
| Mean legacy-field coverage for successful runs | 744 bp |
| Mean quality score for successful runs | 862 bp |

The only failure is `minimal_no_summary.md`: quality correctly routes it to reject and composition
returns `composition_quality_rejected`. This is an observed failure state, not a crash or silent
fallback.

## Enable, disable and rollback

Enable shadow mode only after migration `20260723_17` is applied:

```env
ACKB_IMPORT_PIPELINE_MODE=shadow
```

Rollback is setting the mode back to `disabled` and restarting the parser worker. No Stage 11 schema
migration exists, and the legacy import path is unchanged. Stage 10 data may remain for audit or be
removed through its documented migration rollback while shadow mode is disabled.

## Remaining blockers

- Build and distribute a current KiCad index to online parser workers; empty-index online reports
  cannot evaluate candidate precision.
- Expose comparison reports and failure details through the review API/workspace (Stage 12).
- Replace the precision proxy with human-reviewed accepted/rejected ground truth.
- Review the 18 hashed fixture conflicts and agree field-level acceptance thresholds.
- Run shadow mode on a bounded real-source sample before any authoritative switch.
- Resolve the pre-existing Alembic ORM drift for legacy catalogue indexes/constraints separately;
  Stage 11 does not alter that schema.
