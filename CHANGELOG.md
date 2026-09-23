# Changelog

All notable changes to this project are documented here. Versions follow semantic versioning.

## [1.7.1] - 2026-09-24

### Added

- Custom accent colors can now be saved as reusable personal presets (up to 12
  unique colors per browser profile).
- Saved accent presets can be applied or removed directly from site settings,
  with keyboard-accessible swatches and separate remove controls.
- Saving is disabled for invalid HEX/RGB drafts, duplicates and full palettes.

### Changed

- Appearance preferences storage upgraded to version 2 with automatic migration
  from existing 1.7.0 preferences.

### Compatibility

- Existing theme and accent selections migrate automatically; legacy theme-only
  preferences remain supported. Removing a saved color does not reset the accent.
- No database migration or backend API change is required.

## [1.7.0] - 2026-09-24

### Added

- Unified site settings panel in the application header, login and registration.
- Five selectable UI accent presets: ACKB Green, Cyan, Blue, Violet and Orange.
- Custom RGB/HEX accent picker with a hue/saturation wheel, brightness control
  and keyboard-accessible inputs. Invalid drafts retain the previous valid color.
- Persistent browser-local appearance preferences and a compact live preview.
- Contrast-aware accent text, borders and button foregrounds in both themes.

### Changed

- Theme selection now lives inside the unified site settings interface.
- ACKB brand and PCB colors are separated from customizable UI interaction
  accents; semantic success, warning, danger and information colors stay independent.

### Compatibility

- Existing stored light/dark/system theme preferences migrate automatically.
- No database migration or backend API change is required.
- Preferences remain local to the browser profile and contain no account data.

## [1.6.3] - 2026-09-24

### Added

- Optional "Запомнить на этом устройстве" login mode with persistent browser
  sessions. Both session and CSRF cookies use the same lifetime.
- Remembered sessions use `ACKB_REMEMBERED_SESSION_TTL_DAYS` (30 days by default,
  configurable from 1 to 90). Ordinary login uses browser-session cookies and the
  existing `ACKB_SESSION_TTL_MINUTES` server-side expiry.

### Compatibility

- No database migration is required. Logout and session revocation are unchanged.
- Existing login clients that omit `remember` receive an ordinary session.
- Registration continues to create an ordinary, non-remembered session.
- Browser session restoration may retain session cookies after closing a browser;
  use logout on shared devices. Server-side expiry and revocation always apply.

## [1.6.2] - 2026-09-22

### Added

- Structured editor diagnostics with precise duplicate-slug and specification
  errors, accessible field descriptions and retained request IDs.
- Automatic Decimal-based conversion of compatible specification units, including
  binary byte sizes; bits remain a separate family. Existing definitions retain
  their canonical units while human-entered display values are preserved.
- Focus and centered scrolling to invalid fields after explicit synchronization,
  keyboard save or lifecycle actions; reduced-motion preferences are respected.
  Background autosave never moves focus or scrolls the editor.

### Fixed

- Human values such as `4 МБ` no longer acquire a second canonical unit (`КБ`).
- Ambiguous numeric input and incompatible units now identify the offending field
  instead of reporting a generic catalog conflict. Unrepresentable conversions
  report storage precision/range errors rather than silently rounding.

### Compatibility

- No database migration or new dependency is required.

## [1.6.1] - 2026-09-20

### Added

- Password visibility controls on login and registration fields, with keyboard and
  screen-reader accessible show/hide actions.

## [1.6.0] - 2026-09-12

### Added

- Includes the synchronized editor from 1.5.0 and the reviewed legacy ZIP/XLSX
  importer: private uploads, immutable plans, explicit administrator confirmation,
  draft-only application, resumable jobs and a provenance/license publication gate.
- Conservative model, alias and image matching with source-only corpus reporting.

### Fixed

- Build provenance uses project metadata, the actual Git revision and the current
  build time; legacy environment values cannot silently label new builds as 1.0.1.

### Compatibility

- Apply migrations `20260910_30` (editor synchronization) and `20260911_31`
  (legacy bundles, items, source links and dispatch) after existing `20260910_29`.
- Provision the private legacy bucket and its runtime policy; start `legacy-worker`.
  Deployment and real-corpus application remain explicit operator actions.

## [1.5.0] - 2026-09-11

### Added

- Debounced document synchronization with one content/media/lifecycle coordinator,
  immediate local dirty state, keyboard flush and bounded opt-in draft recovery.
- Database-backed optimistic edit tokens independent of semantic history revisions;
  idempotent new-draft creation and atomic administrator approve-and-publish.
- Explicit conflict comparison and typed alias/tag/slug/specification validation.

### Fixed

- In-flight responses no longer replace newer typed text; trailing text whitespace is retained.
- Image uploads are staged before coordinated attachment, with safe stage-specific diagnostics;
  failed upload reservation/PUT no longer invalidates the component's edit token.
- Autosave no longer produces a history snapshot or audit event for each text edit.

### Compatibility

- Migration `20260910_30` adds edit tokens and durable draft creation keys. Older mutation
  clients must send the latest `edit_token` when semantic revision and token diverge.
- Historical teacher permissions/data remain supported; the UI marks the role as deprecated.
- Unfinished legacy importer is preserved separately and is not part of this change.

## [1.0.1] - 2026-09-05

### Added

- Image lightbox with keyboard navigation, modal focus handling and the largest safe variant.
- Student self-registration, administrator password reset with session revocation, and a
  dedicated administrator account management tab.

### Fixed

- Component gallery and thumbnails keep stable geometry across portrait photos and wide
  schematics, without cropping or stretching the card hero.
- Local frontend builds derive the commit and build date from the checkout and build time;
  deployed builds accept explicit metadata instead of displaying an old release commit.

### Changed

- Consolidated permanent documentation around current architecture, testing, security, import
  validation and a compact operator QA checklist; release-only reports now live in release notes.

### Security

- Frontend and Python development locks use patched Browserslist, pip and pytest releases.

## [1.0.0] - 2026-09-04

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
