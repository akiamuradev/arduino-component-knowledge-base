# Changelog

All notable changes to this project are documented here. Versions follow semantic versioning.

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
