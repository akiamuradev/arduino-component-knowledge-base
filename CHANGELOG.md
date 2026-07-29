# Changelog

All notable changes to this project are documented here. Versions follow semantic versioning.

## [1.0.0] - Unreleased

### Added

- Centralized server-side permissions for students, teachers, database editors and
  administrators, with persisted role grants and expiring editor access.
- Administrator workflows for creating and blocking users, assigning or revoking temporary
  editor access and protecting the last active administrator account.
- A card lifecycle covering drafts, review, requested changes, approval, publication, hiding,
  reversible archival and restoration, with optimistic revision checks.
- Authorship and revision history, immutable published snapshots and teacher correction
  proposals that editors or administrators resolve separately from published content.
- A protected, filterable action journal for authentication, role, card, import and upload
  events, without exposing sensitive event payloads in the user interface.
- An editor import workspace with bounded previews, source-policy validation, ownership checks
  and explicit retry or cancellation actions.
- Production operations documentation and repeatable PostgreSQL backup, verification, restore
  and migration-upgrade recovery drills.

### Changed

- Manual cards can be saved immediately as incomplete drafts: the server assigns a stable
  temporary slug when the address is blank, while publication still enforces complete core
  content.
- Editors can upload and preview component images before the first draft save; owned staged
  uploads are attached atomically when the draft is created.
- Authentication and navigation now derive the current user's roles and permissions from the
  server; the sign-in form no longer offers a client-side role selector.
- User-facing navigation, forms, statuses, errors and empty states are in Russian, while
  administrative sections and actions are hidden when the server denies their permissions.
- The theme control is an accessible menu with light, dark and system modes that persists the
  user's choice and responds to system theme changes.
- Production Compose configuration now uses fail-closed secret and origin validation,
  restricted service exposure, dedicated runtime database privileges and explicit deployment
  preflight checks.
- The release quality gate now requires backend, frontend, integration, browser and container
  checks, including clean installation, database upgrade and restore scenarios.

### Fixed

- Background-job dispatch is persisted and reconciled after broker failures so accepted work is
  not silently lost; safe dispatch health metrics are available to administrators.
- Uploads enforce file signatures, type and size limits, per-user and global quotas, ownership
  boundaries and deterministic cleanup of rejected or stale objects.
- API failures use a consistent Russian error envelope and do not return tracebacks, internal
  service addresses or raw parser exceptions to ordinary users.
- Catalog cards keep long titles, descriptions, tags, model values and source labels within
  their boundaries on desktop and narrow viewports.

### Security

- Server endpoints enforce the permission matrix independently of the client, including
  resource ownership, lifecycle transitions, imports, audit access and user administration.
- Session revocation follows security-sensitive user and role changes; expired editor grants no
  longer authorize editor actions while preserving authorship and audit history.
- Production startup rejects placeholder credentials and unsafe deployment settings before
  serving traffic.

## [0.21.0] - 2026-07-21

### Added

- Repository parser taxonomy, bounded preview/discovery validation and import-quality diagnostics.
- Global pending-upload quotas and deterministic MinIO media retention with dry-run/apply modes.
- X-ray release audit, dependency vulnerability gates and a cross-artifact release contract.
- Full backend, frontend and stateful E2E regression matrix for multiple component images.

### Changed

- Imported components now map into narrower categories and omit untouched unsafe source properties.
- Proxy-aware client identity, administrator-only import/admin surfaces and runtime media hardening.
- Python runtime dependencies are locked with hashes; CI action references and container bases are immutable.
- The supported frontend toolchain is explicitly bounded to Node.js 22-25; CI remains on Node.js 22.

### Fixed

- Reverse-proxy routes now survive backend, frontend and object-storage container recreation
  by refreshing Docker DNS addresses at runtime.
- Generic `request_failed` component creation failures caused by invalid parser output.
- Orphaned MinIO objects left by failed processing or stale uploads.
- Duplicate merge of draft cards now archives the loser without violating the published timestamp
  database invariant.
- Editor thumbnails recover when a renewed signed media URL replaces a failed or expired URL.

### Security

- No known vulnerable Python or production npm dependencies were detected at release time.
- GitHub secret scanning and push protection report no active secret alerts.
- Remaining deployment risks and required external controls are recorded in
  `docs/XRAY_AUDIT_0.21.0.md`.
