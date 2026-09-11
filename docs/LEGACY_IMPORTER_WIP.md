# Legacy importer — paused for ACKB 1.5.0

## Resumed 2026-09-11

The user explicitly resumed importer implementation after editor 1.5.0. Active branch:
`feat/legacy-importer-resumed`, based on editor `0a47132` plus typing fix `ee38d65`.
Original WIP `e5a8e72` remains preserved. The text below this section is historical.

Current reconciliation checkpoint:

- Strict mypy passes across 275 files. All five original typing errors fixed separately.
- Importer migration renumbered to `20260911_31`, after editor `20260910_30`.
- Plans/revalidation include edit tokens; confirmed administrator recorded independently
  of source uploader. Failed items in completed batches can resume without recreating links.
- Legacy provenance panel is conditional, so ordinary editor autosave gains no extra request.
- Non-specification/comparison DOCX tables remain Markdown rather than false specifications.
- Backend 709 passed / 27 skipped; frontend 146 passed; lint/build passed.
- Four isolated PostgreSQL tests passed: importer apply/retry/stale edit, editor sync,
  release upgrade and historical role migration. Importer migration downgrade/upgrade tested.
- Source-only local analysis: 255 rows, 244 targets, 11 collapsed, 239 with workbook
  images, 114 auto / 37 review / 93 unmatched; 358 images, 27 descriptions, zero safely
  classified technical tables. No existing catalog or production mutation.

Remaining implementation plan: strengthen bounded additive merge and table fixtures;
add upload/confirmation/plan/media/UI tests; investigate reference matching differences;
finish retention/admission diagnostics, production configuration and operator runbook.

User explicitly paused this task on 2026-09-10. This branch preserves the unfinished
implementation, not a deployable release. Do not merge it into the 1.5.0 work.

Base on main: `8dfa5deb21d2ae9b66666a33780a52c023f4499d`, bounded pure ZIP/XLSX
analyzer and 11 synthetic tests. The WIP branch adds draft bundle persistence,
admin APIs, worker/dispatch, catalog-aware planning, private-storage provisioning,
media ingestion, license publication gate and an initial UI. No production access,
uploads, catalog apply, publication or deployment were performed.

## Original task and inputs (local, do not commit corpus)

- Specification: `/home/akiamuradev/.codex/attachments/615b0566-abfb-425b-afa6-51b5791a6fb3/pasted-text.txt`
- Authoritative ZIP: `/home/akiamuradev/Загрузки/Микроконтроллеры, модуля, компоненты и проекты.zip`
- Authoritative XLSX: `/home/akiamuradev/Загрузки/Ардуино модуля.xlsx`
- Analysis reference: `/home/akiamuradev/Загрузки/ackb_legacy_import_manifest_v1.json`
- Mapping reference: `/home/akiamuradev/Загрузки/ackb_legacy_import_review.csv`

References are not runtime inputs. Preserve exclusion of contributor column D and
all ПРОЕКТЫ/code; no automatic publication; typed administrator confirmation only.

## Actual source-only analysis so far

255 workbook rows, 244 targets, 11 duplicates collapsed, 239 targets with XLSX
images (all match reference counts). Current conservative matcher: 114 automatic,
37 review, 93 unmatched, versus reference 149/34/61. Needs systematic comparison,
not tuning to force counts. 782 project files ignored; 358 associated images,
27 targets with description, 1 with specifications. Grouped DrawingML anchors work.

## Last checks and known failures

- Pure parser tests: 11 passed.
- Backend full suite: 700 passed, 25 skipped, 3 failed. Failures: metadata table-set
  expectation; bucket provisioning mock expects two instead of three buckets;
  exact protected-route permission contract missing 11 new routes.
- `mypy`: success, 270 source files. `ruff`: success after formatting/fixes.
- Frontend build succeeds; bundle-size warning. ESLint: 23 new-panel errors
  (21 auto-fixable void-arrow style; two nullable template interpolations).
- Frontend: 122 passed, 5 failed in ComponentEditorPage tests. Unconditional
  LegacyLicensePanel adds a GET and consumes sequential fetch mocks. Fix design
  by exposing legacy provenance presence on the card and conditionally mounting,
  then update appropriate mocks; do not disable coverage.
- No integration/migration execution against a real database yet for this WIP.

## Work to resume (audit thoroughly before release)

1. Add isolated PostgreSQL integration tests (own disposable database, no catalog
   apply against existing services), API confirmation/RBAC/CSRF tests, rollback,
   retry/death/resume/idempotence/stale-plan/media-backpressure tests, UI tests.
2. Review processor transaction/recovery semantics; failed item retry is missing
   for a completed bundle; record actual confirming actor, not only upload owner.
   Avoid overwriting user data; never merge published/history-bearing cards.
3. Enforce immutable plan fields robustly; finish retention/cleanup and upload
   admission expiry; validate bounded plans and file sizes, lock contention.
4. Recheck per-card spec/alias limits and shared property-definition unit keys;
   conservative spec conflicts should remain as text with warnings.
5. Finish media diagnostics, safe MIME handling, selected image limit review,
   failure reporting, private bundle policy and proxy timeout verification.
6. Initial UI uses `/workspace/components/...` links incorrectly (must be
   `/admin/components/...`); license banner wording incorrectly says blocked even
   after review. Integrate provenance visibility and review evidence carefully.
7. Analyze real mismatches against both reference files, finish safe CLI/report,
   operator runbook, deployment documentation and final regression.

The next main task is editor synchronization (1.5.0). It may change concurrency,
history, media attachment and lifecycle APIs. Reconcile those changes explicitly
when resuming this importer; do not cherry-pick blindly.
