# Arduino Component Knowledge Base

[![Quality](https://github.com/akiamuradev/arduino-component-knowledge-base/actions/workflows/quality.yml/badge.svg?branch=main)](https://github.com/akiamuradev/arduino-component-knowledge-base/actions/workflows/quality.yml?query=branch%3Amain)
[![License: GNU GPL v3.0 or later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue)](LICENCE)

[![Tests: included](https://img.shields.io/badge/Tests-included-success)](docs/TESTING.md)

![Python](https://img.shields.io/badge/Python-3776AB)
![React](https://img.shields.io/badge/React-149ECA)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6)
![Vite](https://img.shields.io/badge/Vite-646CFF)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![Pydantic](https://img.shields.io/badge/Pydantic-E92063)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00)
![asyncpg](https://img.shields.io/badge/asyncpg-336791)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1)
![Alembic](https://img.shields.io/badge/Alembic-555555)
![Redis](https://img.shields.io/badge/Redis-DC382D)
![Dramatiq](https://img.shields.io/badge/Dramatiq-555555)
![MinIO](https://img.shields.io/badge/MinIO-C72E49)
![Pillow](https://img.shields.io/badge/Pillow-3776AB)
![FFmpeg](https://img.shields.io/badge/FFmpeg-007808)
![nginx](https://img.shields.io/badge/nginx-009639)
![Docker Compose](https://img.shields.io/badge/Docker%20Compose-2496ED)

**English · [Русский](README.ru.md)**

A self-hosted educational catalogue for reviewed information about Arduino-compatible boards,
sensors, actuators, displays, and related electronic components.

## About the project

Arduino Component Knowledge Base (ACKB) gives students a searchable catalogue while teachers,
editors, and administrators maintain the material through a controlled review process. The
current application version is **1.7.5**.

Developed and maintained by [akiamuradev](https://github.com/akiamuradev).

A clean installation contains categories and approved source definitions, but no fabricated or
automatically published cards. Imported material always starts as a draft; it becomes visible to
students only after review, approval, and explicit publication.

## Current capabilities

- A Russian-language, full-width desktop workspace with responsive mobile layout,
  catalogue search, category/difficulty filters, component details and multiple-image galleries.
- Controlled draft → review → approval → explicit publication, immutable published snapshots,
  revision history, hide/archive actions and separate teacher correction proposals.
- A synchronized card editor with optimistic edit tokens and conflict handling; structured
  validation diagnostics, field navigation and explicit conversion between compatible
  specification units. The authenticated filling guide opens in a separate tab without
  replacing the draft.
- Server-enforced `student`, `teacher`, temporary `editor` and `administrator` roles;
  student-only registration, administrator-controlled account/password management, password
  visibility controls and optional remembered login sessions.
- Light/dark/system themes, custom RGB/HEX accents and saved browser-local accent presets.
  Brand colors remain independent of UI accents.
- A public `/license` page with the complete GNU GPL text and neutral institutional affiliation
  blocks linking to МПК ЛГПУ and ЛГПУ.
- A legacy ZIP/XLSX importer with private source uploads, analysis before application,
  administrator review, explicit plan confirmation and draft-only application. Source rights
  must be verified before publication; see the [legacy importer guide](docs/LEGACY_IMPORTER.md).
- Exact/fuzzy duplicate candidates with administrator-only merge decisions. Registered
  Seeed Studio Wiki/KiCad Symbols adapters preserve provenance and license snapshots, but
  external sources are **inactive for new imports**. The evidence-first pipeline remains
  **disabled/shadow**, not an authoritative production import path.
- Private MinIO media with validated image/video processing; PostgreSQL-backed durable job
  dispatch, Redis/Dramatiq workers and reconciliation of interrupted work.
- Audit trail, Argon2id password hashing, opaque server-side sessions, CSRF protection and
  persistent login throttling; the backend is always the authorization authority.
- Provenance-aware image builds, Alembic migrations, production preflight and deployment smoke
  checks, plus backup/restore procedures covering PostgreSQL and private object storage.

These describe the implemented code, not proof of a deployed release. See the release gate below.

## Screenshots

| Catalogue — light theme | Catalogue — dark theme |
|---|---|
| ![ACKB catalogue in the light theme](docs/screenshots/frontend-light-desktop.png) | ![ACKB catalogue in the dark theme](docs/screenshots/frontend-dark-desktop.png) |

| Sign in — mobile light theme | Sign in — mobile dark theme |
|---|---|
| ![ACKB sign-in page on a mobile viewport in the light theme](docs/screenshots/frontend-light-mobile.png) | ![ACKB sign-in page on a mobile viewport in the dark theme](docs/screenshots/frontend-dark-mobile.png) |

The screenshots are generated by the repository's deterministic Playwright scenario; production
code contains no mock catalogue data.

## Architecture

| Layer | Technology |
|---|---|
| Web interface | React 19, TypeScript 6, Vite |
| API and authorization | FastAPI, Pydantic, SQLAlchemy 2, asyncpg |
| Persistent data | PostgreSQL 17 with Alembic migrations |
| Media | Private MinIO buckets, Pillow, FFmpeg |
| Background work | Redis 8 and Dramatiq |
| Edge | nginx and Docker Compose |

```text
Browser -> reverse proxy -> frontend
                         -> backend -> PostgreSQL
                                    -> Redis -> workers
                                    -> private MinIO
```

The backend is the authorization source of truth. Parser output cannot publish a card, and a
duplicate merge always requires a separate administrator decision. See
[Architecture](docs/ARCHITECTURE.md) and [Security](docs/SECURITY.md) for the full boundaries.

## Quick start

Requirements: Docker Engine, the Docker Compose plugin, Git, Python 3.12+, `curl`, and `openssl`. Clone the
default branch into a native Linux filesystem:

```bash
git clone --branch main --single-branch \
  https://github.com/akiamuradev/arduino-component-knowledge-base.git
cd arduino-component-knowledge-base
bash scripts/linux_bootstrap.sh
```

The bootstrap creates an ignored `.env` with random local credentials and mode `0600`, validates
Compose, builds images through `python3 scripts/build_images.py`, starts them with
`docker compose up --no-build --detach`, and waits for health checks. It does not print generated secrets. Open
<http://localhost:8080>.

Verify the deployment:

```bash
docker compose ps -a
curl -f http://127.0.0.1:8080/health
curl -f http://127.0.0.1:8080/ready
python3 scripts/compose_smoke.py
```

`migrate` and `media-init` are one-shot services; `Exited (0)` is their successful state. For an
existing release checkout, preserve its `.env` and volumes:

```bash
git pull --ff-only origin main
docker compose config --quiet
python3 scripts/build_images.py
docker compose up --no-build --detach
python3 scripts/compose_smoke.py
```

Do not replace `.env` while reusing an existing PostgreSQL volume. For production deployment,
backup, restore, and upgrade procedures, use the [Operations guide](docs/OPERATIONS.md).
The commands above are for the local stack, not a production upgrade shortcut. The image builder
requires a clean committed checkout and obtains the version from project metadata and the full
SHA from Git; old `.env` values cannot override site build metadata.

## Create the first administrator

After the stack is healthy:

```bash
docker compose run --rm backend ackb-bootstrap-admin \
  --login admin --display-name "Initial Administrator"
```

Enter the password twice through the TTY. It must contain 12–128 characters and is never accepted
as a command-line argument. Bootstrap is available only while no active administrator exists.

Students can create an account at `/register` with only a login and password; the backend always
assigns the `student` role. Existing administrators manage password resets and additional
administrator accounts in the protected workspace. Password reset revokes all target sessions;
there is no self-service recovery or collection of email, phone, 2FA, or recovery-code data.

## Content workflow

1. An editor or administrator creates a manual draft. Registered Seeed/KiCad adapters remain
   available for controlled validation, but their sources are inactive for new import jobs.
2. The separate legacy ZIP/XLSX workflow analyzes a private bundle and requires administrator
   review and typed confirmation before applying its plan. Repository imports require explicit
   source reactivation under an approved policy. Neither path publishes automatically.
3. The editor completes the card and resolves duplicate candidates.
4. The editor submits it for review; an administrator requests changes or approves it.
5. An administrator explicitly publishes the approved revision.
6. Students see the immutable published snapshot. Later edits begin a new draft; hide and archive
   actions remain reversible.

## Development and checks

Automated backend, frontend, integration and browser tests are included; see [Testing](docs/TESTING.md).

Use Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), Node.js `>=22.12 <26`, npm, and Docker.

Backend and documentation checks:

```bash
uv lock --check
uv sync --frozen --extra dev
uv run ruff check .
uv run ruff format --check src scripts tests migrations
uv run mypy --strict src scripts tests migrations
uv run pytest
uv run python -m build
uv run python scripts/docs_contract.py
uv run python scripts/release_contract.py
uv run python scripts/backend_smoke.py
```

Frontend and browser checks:

```bash
cd frontend
npm ci
npm run audit
npm run lint
npm run typecheck
npm test
npm run build
npm run smoke
npx playwright install chromium
npm run test:e2e
```

Container checks and the PostgreSQL/MinIO integration environment are documented in
[Testing](docs/TESTING.md). The `quality` workflow runs the mandatory CI checks on
every push and pull request; it does not deploy or verify production.

Regenerate the four README screenshots from deterministic test-only fixtures (inside `frontend`):

```bash
ACKB_UPDATE_SCREENSHOTS=1 npm run test:e2e -- --grep "captures approved responsive theme views"
```

Screenshots document the UI; they do not replace layout assertions or production checks.

## Release and deployment gate

A release is complete only when **all mandatory GitHub CI checks succeed**, an authorized
deployment after merge to `main` succeeds, and the running production build is verified.
Check running containers, production smoke tests and site/API metadata against the deployed
checkout: actual version, full Git SHA and actual build date/time. Frontend `/build-info.json`
records version/SHA/build time; backend `/health` exposes the application version. A stale or mismatching
value leaves the release incomplete, even if the application works.

Local tests, CHANGELOG, tags, GitHub Releases or a merged PR are not substitutes for that check.
Report version, full commit SHA, build date, CI status, production smoke result and confirmation
that production serves that exact build. If deployment is not authorized, do not deploy and
explicitly leave the production gate open. See [Contributing](CONTRIBUTING.md) and
[Operations](docs/OPERATIONS.md) for the complete workflow.

## Documentation

- [Requirements](docs/REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data model](docs/DATA_MODEL.md)
- [Testing](docs/TESTING.md)
- [Security controls](docs/SECURITY.md) and [threat model](docs/THREAT_MODEL.md)
- [Operations](docs/OPERATIONS.md) and [deployment](docs/DEPLOYMENT.md)
- [Import validation](docs/IMPORT_VALIDATION.md) and [import roadmap](docs/imports/ROADMAP.md)
- [Data licensing](docs/DATA_LICENSING.md) and [third-party notices](THIRD_PARTY_NOTICES.md)
- [Contributing and forks](CONTRIBUTING.md)

## Contributing and forks

To contribute upstream, create a GitHub fork, clone your fork, add this repository as `upstream`,
and branch from `upstream/main`:

```bash
git clone https://github.com/<username>/arduino-component-knowledge-base.git
cd arduino-component-knowledge-base
git remote add upstream https://github.com/akiamuradev/arduino-component-knowledge-base.git
git fetch upstream
git switch -c feature/<short-name> upstream/main
```

Do not push feature work directly to `main`. Keep one pull request focused on
one task, synchronize with `git fetch upstream`, and run the relevant checks above before opening
a PR. Never commit `.env`, credentials, generated build output, or user data.

An independent fork or derivative remains subject to the
[GNU General Public License v3.0 or later](LICENCE). Imported data
keeps its own license, attribution, and provenance. Replace all credentials before a public
deployment, follow the security/deployment requirements, and do not imply affiliation with
Arduino, Seeed Studio, KiCad, or akiamuradev. Renaming the product requires consistent
updates to branding, package metadata, Compose image names, frontend metadata, versions, and
documentation.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete upstream and independent-fork workflows.

## Security

Never publish credentials, personal data, or exploit details in an issue or pull request. Review
the trust boundaries in [Security](docs/SECURITY.md) before changing authentication, imports,
media, or deployment. A green CI run does not replace TLS, secret rotation, backups, network
policy, monitoring, and the production preflight checks.

## License and third-party material

Application code is distributed under the
[GNU General Public License v3.0 or later](LICENCE). SPDX: `GPL-3.0-or-later`. Copyright © 2026 akiamuradev.

Imported third-party material is not relicensed as application code. See
[Data licensing](docs/DATA_LICENSING.md) and [Third-party notices](THIRD_PARTY_NOTICES.md) for
source-specific licenses, attribution, and provenance requirements.
