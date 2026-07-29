# X-ray audit: 0.21.0

Audit date: 2026-07-21. Scope: tracked source and history, backend/frontend dependencies,
authentication and parser boundaries, migrations, Docker/Compose, CI, documentation and GitHub
repository settings. This is a release-readiness audit, not a penetration test or a production
restore drill.

## Release decision

No critical code vulnerability, committed credential or known vulnerable production dependency
was found. Version 0.21.0 is releasable as an application release. It is not a certification that
the default Compose stack is safe for an untrusted public network: the deployment controls below
remain mandatory.

Release gates added by this audit:

- hashed Python runtime lock plus `uv.lock`; npm already uses `package-lock.json` and `npm ci`;
- immutable GitHub Action SHAs and digest-pinned container bases;
- `pip-audit`, Bandit medium/high and `npm audit` CI gates;
- one release-contract check for backend, frontend, images, env examples, docs and lockfiles;
- weekly Dependabot configuration for Python, npm and GitHub Actions.
- an explicit Node.js `>=22.12 <26` toolchain contract after Node.js 26 exposed an incompatible
  jsdom/Vitest `localStorage` environment; the supported Node.js 22 CI path remains authoritative.

## Open findings

### Closed after the audit

- Stage 16 added separate PostgreSQL migration/runtime identities, repeatable no-DDL runtime
  grants, a bucket-scoped MinIO application identity, Redis authentication, exact trusted Host,
  production fail-closed validation and read-only/drop-capability profiles for application/init
  and edge containers.
- Stage 17 added a SELECT-only PostgreSQL backup identity, private custom-format dump with
  checksum/data manifest, isolated fail-closed restore and an automated clean-install,
  previous-head upgrade and restore drill. The remaining availability finding is MinIO binary
  backup and cross-store consistency, not PostgreSQL recovery.

### High

1. Queue publication happens after the database commit without a transactional outbox or a
   reconciler. A broker outage can leave a durable `queued` import/media job unpublished until an
   operator/client retries it. Add an outbox dispatcher or a periodic queued-job reconciler.
2. PostgreSQL backup and restore are automated and proven, but MinIO object backup,
   PostgreSQL/MinIO consistency orchestration and deployment-specific encrypted off-host storage
   remain open. Production rollout remains blocked until the operator supplies and tests the
   complete cross-store recovery control.
3. Parser egress is constrained by application allowlists and SSRF validation, but the Compose
   `parser-egress` network does not itself enforce DNS/HTTPS-only destinations. A host firewall or
   network policy is still required as an independent containment layer.

### Medium

1. GitHub `main` has no branch protection/ruleset. A maintainer can bypass the green workflow or
   delete/rewrite release history. Require the five quality jobs, block force pushes/deletion and
   require reviewed pull requests when the contributor workflow permits it.
2. GitHub code scanning and Dependabot alerts were unavailable during the audit; security updates
   were disabled at repository level. The committed Dependabot configuration does not replace
   enabling those repository features.
3. Container vulnerability scanning, SBOM/provenance generation and signed image publication are
   not part of CI. Base images are digest-pinned, which limits drift but does not detect newly
   disclosed CVEs.
4. Backend line coverage measured 70%. Important orchestration paths remain weakly exercised:
   import processor 16%, image processor 18%, video processor 24%, catalog service 41%, and
   several API/repository modules around 36-57%. Frontend coverage is not enforced in CI.
5. External edge rate limiting, centralized monitoring/alerting, audit/session retention periods
   and capacity budgets still depend on deployment decisions.
6. Media retention examines a bounded prefix per run. At inventories above the scan limit, a
   continuation cursor or rotating scan strategy is needed to prevent long-lived orphan starvation.

### Low / maintainability

1. Smoke scripts use Python `assert`; running them with `python -O` disables their checks.
2. `scripts/production_smoke.py` has two unused redirect-handler arguments reported by Vulture.
3. `catalog/service.py`, `ComponentEditorPage.tsx`, `api/catalog.py`, import acquisition/repository
   modules and the global stylesheet are large change hotspots and should be split by responsibility.
4. Secret heuristics flag repeated test placeholders. A reviewed detect-secrets baseline would
   reduce noise while keeping GitHub push protection as the enforcement boundary.

## Evidence

- Existing GitHub quality run for the pre-release baseline passed backend, frontend, integration,
  containers and e2e jobs.
- Local unit run: 254 passed, 3 integration tests skipped; the repository-policy test fails only
  while the intentionally ignored developer `.env` file exists.
- Python `pip-audit`: no known vulnerabilities. npm audit (production and full tree): zero known
  vulnerabilities. Bandit: no medium/high finding in `src/arduino_component_kb`.
- GitHub secret scanning and push protection are enabled; open secret alerts: zero.
- Alembic has one linear head, `20260721_16`; the running stack reported that same head during the
  release audit.

## Required production sign-off

The release may be deployed to the validated internal environment only after the operator records:
separate infrastructure identities, backup and successful restore evidence, host firewall/egress
rules, monitoring/alerts, TLS preflight, external rate limiting and an approved data-source rights
decision. These controls are outside the application release artifact and must not be inferred from
a green CI run.
