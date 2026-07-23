# Evidence-first import review workspace

Stage 12 exposes the persisted evidence-first draft to administrators without making the new
pipeline authoritative. Draft, facts, identity, quality and candidate payloads remain immutable.
Reviewer choices are stored in a separate versioned state and every accepted mutation appends both
a workspace action and the existing application audit event.

## API projection

`GET /api/v1/admin/import-reviews/{review_draft_id}` returns:

- normalized facts and source provenance;
- field-level confidence from the composed draft;
- all persisted identity candidates and the selected candidate;
- the complete quality report, issues and route;
- unmapped specifications, normalization conflicts and taxonomy options;
- KiCad enrichment lifecycle, effective relation, evidence and score breakdown;
- module connection, internal components and KiCad symbols as separate structures;
- parser issues and the append-only reviewer action history.

The response never projects KiCad symbol pins into `module_connection.pins`. The frontend renders
three independent panels: ready-module connection, internal electronic components, and KiCad
symbol/footprint data. KiCad pins are labelled as symbol pins.

The queue endpoint is `GET /api/v1/admin/import-reviews?status=pending`. All endpoints are
administrator-only and responses use `Cache-Control: no-store`.

## Reviewer actions

| Action | Endpoint suffix | Durable effect |
| --- | --- | --- |
| Accept/reject enrichment | `/enrichments/{id}/decision` | Updates lifecycle and appends both enrichment and workspace audit records |
| Change relation | `/enrichments/{id}/relation` | Changes only the effective relation column; immutable candidate payload is retained |
| Select identity | `/identity` | Selects a candidate belonging to the same artifact |
| Map specification | `/specification-mappings` | Stores a mapping from an opaque stable spec key to a known taxonomy path |
| Mark parser issue | `/parser-issues` | Stores a bounded machine code and reviewer note |
| Confirm draft | `/confirm` | Freezes review state after all enrichments and unmapped specs are resolved |

Every mutation requires:

- administrator RBAC;
- same-origin session and CSRF token;
- `expected_revision` optimistic concurrency;
- a bounded human reason or note.

State starts virtually at revision 1. The first mutation creates and locks
`import_review_states`; each successful action increments the revision and inserts one
`import_review_actions` row. A stale browser receives `409 import_review_revision_conflict`.
Confirmed drafts are immutable to this API.

Confirmation does not publish a catalogue card, attach a component or switch the pipeline. It only
records that the evidence-first draft has passed human review. Stage 13 can use this explicit state
for acceptance metrics; the legacy worker and catalogue workflow remain unchanged.

## Schema and rollback

Revision `20260723_18` adds:

- `import_review_states` — one mutable, optimistic-lock state per immutable draft;
- `import_review_actions` — append-only reviewer decisions with previous/resulting safe values.

Upgrade:

```bash
alembic upgrade 20260723_18
```

Rollback:

```bash
alembic downgrade 20260723_17
```

Before downgrade, disable access to the Stage 12 routes and export the two tables if review history
must be retained. Rollback drops only Stage 12 state/audit; Stage 10 snapshots and legacy catalogue
records remain intact.

## Verification

```bash
pytest -q tests/test_import_review_api.py tests/test_security.py tests/test_migrations.py
ACKB_RUN_INTEGRATION=1 pytest -q tests/integration/test_import_review_postgresql.py
cd frontend
npm test -- --run src/pages/ImportReviewPage.test.tsx src/app/routes.test.tsx
```

The PostgreSQL test proves relation change, stale revision rejection, accept audit, parser issue,
confirmation and immutable enrichment payload preservation in one transaction.
