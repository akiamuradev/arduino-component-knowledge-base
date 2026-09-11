# ACKB 1.5.0 — synchronized editor implementation

## Isolation

Unfinished importer is preserved exactly in branch `wip/legacy-importer-20260910`,
commit `e5a8e72`, with recovery notes `docs/LEGACY_IMPORTER_WIP.md` on that branch.
This task starts from main `8dfa5de` in `feat/editor-sync-1.5.0`; importer WIP is
not included. No production access/deployment is authorized or performed.

Full task: local attachment
`/home/akiamuradev/.codex/attachments/ef634f12-2d6d-47f6-8e51-139bb10ab357/pasted-text.txt`.

## Diagnosis

- Content uses independent React Query mutations with a captured card revision;
  no synchronous single-flight guard. Images have another captured revision and
  update it independently. Lifecycle neither flushes text nor joins their queue.
- Alias/tag NFKC/casefold duplicates raise untyped CatalogValidationError; the
  generic conflict response does not tell the user which field was invalid.
- Component-bound upload reservation already attaches/touches history before PUT
  and completion. A failed PUT leaves the form's captured revision stale. This is
  a reproducible code-path race, not proof of a specific remote MinIO outage.
- New draft state has no recovery. Every content update produces a history snapshot
  and audit entry, unsuitable for debounce-driven autosave.
- Text serialization trims values and the editor remounts after initial creation;
  both need careful handling to preserve edits made while requests are in flight.

## Chosen design / checkpoints

1. Separate server `edit_token` from semantic `revision`; database-managed token
   covers all component mutations. Autosave does not emit history/audit per tick.
2. Atomic document synchronization (content + image metadata/attachment) with
   exact token, idempotent initial creation, typed field validation.
3. One editor controller owns snapshots, generation, token, debounce, retries,
   local recovery and serialized lifecycle flush. Never apply old response text.
4. Existing private staged upload path, followed by coordinated attachment, avoids
   a reservation changing the component. Stage-specific safe error diagnostics.
5. Atomic administrator approve-and-publish preserving semantic events; legacy
   teacher compatibility retained but removed from ordinary assignable UI.
6. Focused tests, full regressions, isolated PostgreSQL migration/integration tests,
   release metadata only once coherent; no GitHub Release and no deployment.

## Implementation and acceptance report

### Document owner and concurrency

`frontend/src/editor/sync-controller.ts` owns the raw local snapshot, acknowledged
generation, debounce timer (750 ms), synchronous single-flight promise, creation
key and current server edit token. A response acknowledges only its sent generation;
it never replaces newer text. Pending changes coalesce into the next request with
the returned token. Content, image metadata and lifecycle all use this owner.
Ctrl/Cmd+S flushes; in-app navigation flushes or stays on the editor after an error.
Browser unload warns only for dirty content or active binary uploads. Uploads also
block lifecycle/navigation until the completed assets join document synchronization.

The database trigger advances the token for every component-row update, including
older mutation paths. A document PUT locks the row and checks the exact token;
content and image changes commit together. The token may advance more than once
within a single transaction and must never be treated as a history version.
Conflict stops automatic writes, retains local content, reads the current server
card into a separate comparison view and requires an explicit reload/discard.
No force-write or silent merge is implemented.

### History, creation and recovery

Autosave does not create revision snapshots or audit events per text edit. Creation
has one semantic event; lifecycle retains semantic snapshots; image membership
changes have a bounded event per synchronization, not per caption keystroke.
Approve-and-publish writes approval and publication events in one transaction;
publication validation failure rolls back approval too. Published snapshots remain
immutable while a new working draft is synchronized.

An untouched new form issues no POST. First mutation creates a draft using a UUID
idempotency key protected by a transaction advisory lock and durable
`editor_creations` record. A lost/retried response returns that same component.
The controller then synchronizes the newest local state before canonical-route
navigation. Recoverable snapshots store an acquired component ID, preventing a
second POST after a successful creation followed by a failed sync.

Recovery uses per-user/per-component localStorage keys, schema version 1, a seven-day
TTL, at most eight entries and at most 512,000 JSON characters per entry. It contains
document metadata/text and concurrency identifiers, not credentials, auth/session
tokens, signed storage URLs or file bytes. Recovery requires explicit choice; stale
base tokens stop synchronization. Corrupt/unsupported/expired entries are ignored;
storage failure leaves the editor functional with an honest warning. Identity
replacement/logout clears recovery. Late disposed-controller responses cannot
repopulate it. This is device-local recovery, not a server backup or cross-device sync.

### Media and validation

The browser uses existing unbound private reservation → PUT → completion → processing
status, then shared document attachment. The old component-bound reservation was
the reproducible source of premature revision advancement on failed uploads; this
change does not claim diagnosis of a particular production storage/network outage.
Quarantine, processing dispatch, ownership, readiness checks, retention, MIME and
size limits remain enforced. Metadata, captions, order, primary selection and removal
have no separate save action. Reservation/upload/confirmation/processing failures
show a stage, safe code and request ID where available, never presigned URLs.
Attachment failures are surfaced by document synchronization and preserve local data.

Alias/tag validation identifies duplicate pairs with NFKC/case-insensitive matching,
including the real Arduino Uno Rev3 / Arduino UNO Rev3 case. The backend remains
authoritative for Unicode normalization and returns typed 422 field failures rather
than misclassifying them as revision conflicts. Client-known invalid values block
autosave until corrected; slug and description validation are field-associated,
and existing specification row validation is retained.

### Lifecycle, roles and compatibility

Editor submit flushes the newest document first. The administrator action
«Одобрить и опубликовать» requires both review and publish permissions server-side.
Generic command dispatch independently checks each action's permission. New routes
retain authentication and CSRF dependencies. Historical teacher role grants and
teacher-only learning fields are unchanged; the UI labels the role as deprecated
and does not introduce it into normal role assignment.

Migration: `migrations/versions/20260910_30_editor_sync.py`, based on `_29`;
adds/backfills `components.edit_token`, its trigger, and `editor_creations`.
No existing component content is rewritten. Downgrade removes synchronization
metadata, so do not run mixed old/new application instances across a downgrade.

API additions (all under `/api/v1/workspace`):

- `POST /editor-drafts`: `creation_key` plus incomplete draft fields.
- `PUT /components/{id}/sync`: `edit_token`, content and complete requested image set.
- `POST /components/{id}/commands/{action}`: exact token and action-specific permission.
- `POST /components/{id}/approve-and-publish`: exact token and both permissions.

Workspace card responses now carry `edit_token`. Existing mutation endpoints accept
an optional token in addition to semantic revision. A revision-only client is rejected
once token and revision diverge: it must reload and send the token, not retry blindly.
Existing manual API edits still create semantic history. Deployment must apply the
migration before serving the new API/frontend; no production rollout was performed.

### Changed-file map

- Backend: catalog domain/models/service, `catalog/synchronization.py`,
  `api/catalog.py`, `api/component_sync.py`, router registration and migration.
- Frontend: `editor/{recovery,sync-controller,use-component-sync}`, editor page,
  image editor, API contracts/errors, session cache, role labels and narrow-layout CSS.
- Regression: controller/page/image/browser/security tests; disposable PostgreSQL
  acceptance, migration/upgrade/role checks and head expectations in operator smoke scripts.
- Release: Python/frontend package and lock metadata, defaults, Compose image tags,
  environment examples, READMEs and CHANGELOG synchronized to 1.5.0.

### Verification

- Backend full suite: **700 passed, 26 skipped** (integration tests opt in separately).
- Disposable PostgreSQL editor acceptance + upgrade + existing-role migration:
  **3 passed**. Includes parallel idempotent creation, competing exact-token writes,
  autosave history bounds, upload reservation isolation, atomic publication rollback
  and preservation of a published snapshot after a working edit.
- Frontend unit/component tests: **146 passed**, across 30 files.
- Production frontend build, ESLint, TypeScript and distribution smoke: passed.
- Ruff check and format check: passed; release contract for 1.5.0: passed.
- Full mypy: **five pre-existing errors in `legacy/parser.py` and
  `tests/test_legacy_parser.py`**, no new editor errors. These files are unchanged from
  `8dfa5de`; importer work was deliberately not resumed. CI is therefore not claimed green.
- Chromium browser regression: **14 passed, 1 skipped** (opt-in visual captures).
  Includes multi-image synchronization/publication, immutable public media, keyboard
  and responsive accessibility at 320 px; fixed the outer fieldset's narrow-layout overflow.
- `uv lock --check`: passed. Bandit reports **one existing medium B314 finding**
  at `legacy/parser.py:165` (ElementTree parsing), outside this editor change.
- Build warning: frontend entry chunk is approximately 548 kB minified (158 kB gzip),
  above Vite's advisory 500 kB threshold; build succeeds. No bundle-size warning suppression.

Importer WIP remains at `e5a8e72` on `wip/legacy-importer-20260910`, separately pushed.
No production database was accessed or migrated, no deployment or GitHub Release
was performed. Integration databases are newly created disposable databases only.
