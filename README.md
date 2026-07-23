# Arduino Component Knowledge Base

[![Quality](https://github.com/akiamuradev/arduino-component-knowledge-base/actions/workflows/quality.yml/badge.svg)](https://github.com/akiamuradev/arduino-component-knowledge-base/actions/workflows/quality.yml)
[![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-4c566a)](LICENCE)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-20232A?logo=react&logoColor=61DAFB)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-8-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![MinIO](https://img.shields.io/badge/MinIO-private%20media-C72E49?logo=minio&logoColor=white)](https://min.io/)
[![Dramatiq](https://img.shields.io/badge/Dramatiq-background%20jobs-222222)](https://dramatiq.io/)
[![Alembic](https://img.shields.io/badge/Alembic-schema%20migrations-6BA81E)](https://alembic.sqlalchemy.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)

**[English](#english) · [Русский](#русский)**

---

<a id="english"></a>

## English

### Overview

Arduino Component Knowledge Base is a self-hosted educational platform for maintaining a
reviewed catalogue of Arduino-compatible boards, sensors, actuators, displays and related
components. Students browse published learning material; teachers prepare drafts; administrators
control users, duplicate decisions and operational jobs.

The application is currently at version **0.21.0**. Its backend, frontend, workers, migrations,
media storage and reverse proxy form a runnable Docker Compose stack. A new database intentionally
contains categories and approved source definitions but **no fabricated or automatically published
component cards**. Cards become visible in the student catalogue only after editorial review and
explicit publication.

### Implemented capabilities

- responsive React interface with light, dark and system themes;
- student catalogue, full-text search, filters and component detail pages;
- teacher/administrator dashboard, card editor, preview, publish and archive workflow;
- FastAPI application factory, async SQLAlchemy/asyncpg and PostgreSQL readiness checks;
- Argon2id passwords, opaque server-side sessions, CSRF protection, RBAC, audit events and
  brute-force throttling;
- immutable published revisions and optimistic conflict handling;
- private MinIO image/video storage with presigned uploads and PostgreSQL metadata;
- MIME/magic-byte validation, Pillow image variants, SHA-256/pHash and FFmpeg H.264/AAC
  renditions with posters;
- Redis + Dramatiq background jobs with durable PostgreSQL status, progress, retries and
  idempotency;
- administrator import workspace with bounded discovery, preview and draft job monitoring;
- versioned, SSRF-resistant Seeed Studio Wiki and KiCad Symbols adapters;
- exact and fuzzy duplicate detection; only an administrator can confirm merge decisions;
- Docker Compose deployment with PostgreSQL, Redis and MinIO isolated from host ports.

### Stack and trust boundaries

| Layer | Technology | Responsibility |
|---|---|---|
| Frontend | React 19, TypeScript 6, Vite, React Router, TanStack Query | Student and editorial UI |
| Backend | FastAPI, Pydantic, SQLAlchemy 2, asyncpg | API, validation and authorization source of truth |
| Database | PostgreSQL 17 | Domain data, media metadata, sessions, audit and durable jobs |
| Binary media | Private MinIO buckets | Original uploads, safe variants, video renditions and posters |
| Jobs | Redis 8 + Dramatiq | Media and import task delivery |
| Schema | Alembic only | All PostgreSQL schema changes; runtime `create_all` is forbidden |
| Edge | nginx + Docker Compose | Same-origin frontend/API routing and the only published host port |

```text
Browser -> reverse proxy -> React frontend
                         -> FastAPI -> PostgreSQL
                                    -> Redis -> Dramatiq workers
                                    -> private MinIO

Allowed source URL -> parser worker -> reviewed draft -> teacher/admin -> published revision
```

The backend is always the authorization source of truth. Frontend route guards are only a user
experience feature. Parser output cannot publish a component, and duplicate merge requires a
separate administrator decision.

### Roles

| Action | Student | Teacher | Administrator |
|---|:---:|:---:|:---:|
| Browse published cards | Yes | Yes | Yes |
| Create and edit drafts | No | Yes | Yes |
| Start a repository import | No | No | Yes |
| Publish/archive a reviewed card | No | Yes | Yes |
| Manage users and roles | No | No | Yes |
| Confirm duplicate merge | No | No | Yes |
| Monitor/retry all background jobs | No | No | Yes |

### Data sources and licensing

New imports are limited to two registered repositories:

1. [Seeed Studio Wiki](https://github.com/Seeed-Studio/wiki-documents) — `GPL-3.0-only`;
2. [Official KiCad Symbols](https://gitlab.com/kicad/libraries/kicad-symbols) — `CC-BY-SA-4.0`.

The historical Arduino-Tex and Portal-PK records are inactive. AlexGyver is disabled because use
was denied by the source owner. None of these three website sources can be launched from the UI or
repository import API. Acquisition is bounded to registered repositories, paths and revisions;
scripts, hooks and documentation builds are never executed. An import produces a preview and then
only a `draft`, never a published card.

The PolyForm license applies to application code, not imported third-party data. Each imported
card retains an immutable source, commit, file/entry, parser version, license, attribution and
modifications snapshot. See [Data licensing](docs/DATA_LICENSING.md) and
[Third-party notices](THIRD_PARTY_NOTICES.md). This project is not affiliated with Arduino, Seeed
Studio or KiCad; names and trademarks belong to their respective owners.

### Quick start on a Linux VM

Requirements: Docker Engine, the Docker Compose plugin, Git, `curl` and `openssl`. Clone into a
native Linux filesystem rather than a Windows/shared mount so file permissions work correctly.

```bash
git clone https://github.com/akiamuradev/arduino-component-knowledge-base.git
cd arduino-component-knowledge-base
bash scripts/linux_bootstrap.sh
```

The bootstrap script creates an ignored `.env` with random local credentials and mode `0600`,
validates Compose, builds the stack and waits for `/health`, `/ready` and the frontend. It never
prints generated secrets. Open <http://localhost:8080> inside the VM.

Check the deployment:

```bash
docker compose ps -a
curl -f http://127.0.0.1:8080/health
curl -f http://127.0.0.1:8080/ready
python3 scripts/compose_smoke.py
```

`migrate` and `media-init` are one-shot services: `Exited (0)` is their expected successful state.
Runtime services should be `Up`/`healthy`. Only reverse proxy publishes port 8080 through the
host-facing `ingress` network; `edge` and `data` remain internal.

Create the first administrator after a healthy start:

```bash
docker compose run --rm backend ackb-bootstrap-admin \
  --login admin --display-name "Initial Administrator"
```

The password is entered twice through the TTY and must contain 12 to 128 characters. It is never
accepted as a command-line argument. The bootstrap command works only while no active administrator
exists.

For an existing checkout, preserve its `.env` and volumes:

```bash
git pull --ff-only origin main
docker compose -f compose.yaml up --build -d
python3 scripts/compose_smoke.py
```

Do not replace `.env` when reusing an existing PostgreSQL volume: the database role password is
established when the volume is first initialized.

### Content workflow

1. Sign in as a teacher or administrator to create a manual draft.
2. An administrator may open **Administration → Import**, select Seeed or KiCad, perform bounded
   discovery and inspect the normalized preview.
3. Click **Create draft** to enqueue the selected entry, then review and complete the resulting
   draft in the editor.
4. Resolve any duplicate candidate; merge confirmation is administrator-only.
5. Preview and explicitly publish the card.
6. The immutable published snapshot becomes available in the student catalogue.

A clean installation shows an empty catalogue until the first reviewed draft is explicitly
published. Importing never performs that publication step.

### Development and verification

Backend requirements: Python 3.12+, PostgreSQL, Redis, MinIO, FFmpeg and ffprobe. Frontend requires
Node.js 22+ and npm.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
ruff check .
ruff format --check src scripts tests migrations
mypy --strict src scripts tests migrations
pytest
python -m build
python scripts/docs_contract.py
python scripts/backend_smoke.py

cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run smoke
npm run test:e2e
```

GitHub Actions runs backend lint/type/tests/build, frontend lint/type/tests/build, Playwright E2E,
PostgreSQL/MinIO integration tests and container contract/build jobs on every push and pull request.

### API overview

| Prefix or endpoint | Purpose |
|---|---|
| `/health`, `/ready` | Process liveness and bounded PostgreSQL readiness |
| `/api/v1/auth/*` | Login, current backend-resolved principal and logout |
| `/api/v1/catalog/*` | Published student catalogue and source registry |
| `/api/v1/workspace/*` | Teacher/administrator card and category workspace |
| `/api/v1/media/*` | Private upload reservation, completion and processing status |
| `/api/v1/import-jobs/repository/*` | Administrator discovery, preview and durable draft jobs |
| `/api/v1/admin/*` | Users, job monitor and duplicate decisions |
| `/api/v1/openapi.json` | Versioned OpenAPI contract |

Interactive API documentation is disabled by default. Local `.env` enables it at `/docs`; never
enable it merely to bypass production access controls.

### Documentation

- [Requirements](docs/REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Evidence-first import roadmap](docs/imports/ROADMAP.md)
- [Data model](docs/DATA_MODEL.md)
- [Security controls](docs/SECURITY.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Testing](docs/TESTING.md)
- [Data licensing](docs/DATA_LICENSING.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
- [Corporate Ubuntu deployment](docs/DEPLOYMENT.md)
- [Frontend guide](frontend/README.md)

### License

The project is distributed under the
[PolyForm Noncommercial License 1.0.0](LICENCE). Commercial use is not permitted by this license;
permitted noncommercial use is governed by the license text.

Third-party data remains under the license recorded in its source snapshot; it is not relicensed
under PolyForm by inclusion in this application.

[Back to language selector](#arduino-component-knowledge-base)

---

<a id="русский"></a>

## Русский

### О проекте

Arduino Component Knowledge Base — самостоятельная образовательная web-платформа для ведения
проверенного каталога Arduino-совместимых плат, датчиков, исполнительных устройств, дисплеев и
других компонентов. Студенты читают опубликованные материалы, преподаватели готовят черновики,
администраторы управляют пользователями, решениями по дубликатам и фоновыми задачами.

Текущая версия — **0.21.0**. Backend, frontend, workers, миграции, media storage и reverse proxy
собираются в единый рабочий Docker Compose-контур. Новая база намеренно содержит категории и
описания разрешённых источников, но **не содержит вымышленных или автоматически опубликованных
карточек**. Карточка появляется в студенческом каталоге только после редакционной проверки и явной
публикации.

### Реализовано

- адаптивный React-интерфейс со светлой, тёмной и системной темами;
- студенческий каталог, полнотекстовый поиск, фильтры и страницы компонентов;
- dashboard преподавателя/администратора, редактор, preview, публикация и архивирование;
- FastAPI application factory, async SQLAlchemy/asyncpg и PostgreSQL readiness;
- Argon2id, opaque server-side sessions, CSRF, backend RBAC, audit и brute-force protection;
- неизменяемые опубликованные revisions и optimistic conflict handling;
- private MinIO для изображений и видео, presigned upload и metadata в PostgreSQL;
- MIME/magic bytes, Pillow variants, SHA-256/pHash, FFmpeg H.264/AAC rendition и poster;
- Redis + Dramatiq с durable status/progress, retry/backoff и idempotency;
- рабочее место administrator для bounded discovery, preview и мониторинга draft job;
- версионированные SSRF-safe adapters Seeed Studio Wiki и KiCad Symbols;
- exact/fuzzy дедупликация; merge всегда отдельно подтверждает administrator;
- Docker Compose, в котором PostgreSQL, Redis и MinIO не публикуются на host.

### Стек и границы доверия

| Слой | Технологии | Назначение |
|---|---|---|
| Frontend | React 19, TypeScript 6, Vite, React Router, TanStack Query | Student и editorial UI |
| Backend | FastAPI, Pydantic, SQLAlchemy 2, asyncpg | API, валидация и источник истины для авторизации |
| База | PostgreSQL 17 | Карточки, metadata, sessions, audit и durable jobs |
| Binary media | Private MinIO buckets | Загрузки, безопасные варианты, видео и posters |
| Очереди | Redis 8 + Dramatiq | Доставка media/import задач |
| Схема | Только Alembic | Все изменения PostgreSQL; runtime `create_all` запрещён |
| Edge | nginx + Docker Compose | Same-origin маршрутизация и единственный опубликованный порт |

```text
Браузер -> reverse proxy -> React frontend
                          -> FastAPI -> PostgreSQL
                                     -> Redis -> Dramatiq workers
                                     -> private MinIO

Разрешённый URL -> parser worker -> проверяемый draft -> teacher/admin -> published revision
```

Backend всегда является источником истины для авторизации. Frontend guards только улучшают UX.
Parser не может публиковать карточку, а duplicate merge требует отдельного решения administrator.

### Роли

| Действие | Student | Teacher | Administrator |
|---|:---:|:---:|:---:|
| Просмотр опубликованных карточек | Да | Да | Да |
| Создание и редактирование draft | Нет | Да | Да |
| Запуск repository import | Нет | Нет | Да |
| Публикация/архивирование после проверки | Нет | Да | Да |
| Управление пользователями и ролями | Нет | Нет | Да |
| Подтверждение merge дубликатов | Нет | Нет | Да |
| Мониторинг/retry всех фоновых задач | Нет | Нет | Да |

### Источники данных и лицензирование

Новый импорт ограничен двумя зарегистрированными репозиториями:

1. [Seeed Studio Wiki](https://github.com/Seeed-Studio/wiki-documents) — `GPL-3.0-only`;
2. [Official KiCad Symbols](https://gitlab.com/kicad/libraries/kicad-symbols) — `CC-BY-SA-4.0`.

Исторические записи Arduino-Tex и Portal-PK неактивны. AlexGyver отключён, поскольку владелец
источника запретил использование материалов. Ни один из этих трёх website-источников нельзя
запустить через UI или repository import API. Получение ограничено зарегистрированными repository,
путями и revisions; scripts, hooks и сборка документации не запускаются. Импорт сначала создаёт
preview, а затем только `draft`, но никогда не публикует карточку.

PolyForm относится к коду приложения, а не к импортированным сторонним данным. Карточка хранит
неизменяемый snapshot источника, commit, файла/entry, parser version, лицензии, attribution и
преобразований. См. [Лицензирование данных](docs/DATA_LICENSING.md) и
[уведомления о сторонних материалах](THIRD_PARTY_NOTICES.md). Проект не аффилирован с Arduino,
Seeed Studio или KiCad; названия и товарные знаки принадлежат соответствующим правообладателям.

### Быстрый запуск в Linux VM

Нужны Docker Engine, Compose plugin, Git, `curl` и `openssl`. Клонируйте проект в Linux filesystem,
а не в Windows/shared mount, чтобы корректно работали права файлов.

```bash
git clone https://github.com/akiamuradev/arduino-component-knowledge-base.git
cd arduino-component-knowledge-base
bash scripts/linux_bootstrap.sh
```

Bootstrap создаёт ignored `.env` со случайными local credentials и mode `0600`, проверяет Compose,
собирает stack и ждёт frontend, `/health` и `/ready`. Секреты в вывод не попадают. Внутри VM
откройте <http://localhost:8080>.

Проверка:

```bash
docker compose ps -a
curl -f http://127.0.0.1:8080/health
curl -f http://127.0.0.1:8080/ready
python3 scripts/compose_smoke.py
```

`migrate` и `media-init` — одноразовые services; `Exited (0)` для них означает успех. Остальные
services должны быть `Up`/`healthy`. Только reverse proxy публикует 8080 через host-facing сеть
`ingress`; `edge` и `data` остаются internal.

Создание первого administrator после healthy startup:

```bash
docker compose run --rm backend ackb-bootstrap-admin \
  --login admin --display-name "Initial Administrator"
```

Пароль вводится дважды через TTY, содержит от 12 до 128 символов и не передаётся аргументом
командной строки. Bootstrap работает только пока в базе нет активного administrator.

Обновление существующей установки с сохранением `.env` и volumes:

```bash
git pull --ff-only origin main
docker compose -f compose.yaml up --build -d
python3 scripts/compose_smoke.py
```

Не заменяйте `.env`, если используется существующий PostgreSQL volume: пароль database role
устанавливается при первой инициализации volume.

### Наполнение каталога

1. Войдите как teacher или administrator, чтобы создать ручной draft.
2. Administrator может открыть **Администрирование → Импорт**, выбрать Seeed или KiCad,
   выполнить ограниченный поиск и проверить нормализованный preview.
3. Нажмите **Создать черновик**, дождитесь job и проверьте полученный draft в редакторе.
4. Разберите найденный duplicate candidate; merge подтверждает только administrator.
5. Откройте preview и явно опубликуйте карточку.
6. Immutable published snapshot появится в студенческом каталоге.

Чистая установка показывает пустой каталог до первой проверенной и явно опубликованной карточки.
Импорт сам по себе публикацию не выполняет.

### Разработка и проверки

Backend требует Python 3.12+, PostgreSQL, Redis, MinIO, FFmpeg и ffprobe. Frontend требует Node.js
22+ и npm.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
ruff check .
ruff format --check src scripts tests migrations
mypy --strict src scripts tests migrations
pytest
python -m build
python scripts/docs_contract.py
python scripts/backend_smoke.py

cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run smoke
npm run test:e2e
```

GitHub Actions на каждый push и pull request запускает backend lint/type/tests/build, frontend
lint/type/tests/build, Playwright E2E, PostgreSQL/MinIO integration и container contract/build jobs.

### Обзор API

| Prefix или endpoint | Назначение |
|---|---|
| `/health`, `/ready` | Liveness процесса и bounded PostgreSQL readiness |
| `/api/v1/auth/*` | Login, backend-resolved principal и logout |
| `/api/v1/catalog/*` | Опубликованный студенческий каталог и реестр источников |
| `/api/v1/workspace/*` | Карточки и категории teacher/administrator |
| `/api/v1/media/*` | Private upload, completion и processing status |
| `/api/v1/import-jobs/repository/*` | Administrator discovery, preview и durable draft jobs |
| `/api/v1/admin/*` | Пользователи, job monitor и duplicate decisions |
| `/api/v1/openapi.json` | Версионированный OpenAPI contract |

Interactive API documentation по умолчанию выключена. Локальный `.env` включает `/docs`; её нельзя
включать как способ обхода production access controls.

### Документация

- [Требования](docs/REQUIREMENTS.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [ROADMAP evidence-first импорта](docs/imports/ROADMAP.md)
- [Модель данных](docs/DATA_MODEL.md)
- [Контроли безопасности](docs/SECURITY.md)
- [Модель угроз](docs/THREAT_MODEL.md)
- [Тестирование](docs/TESTING.md)
- [Лицензирование данных](docs/DATA_LICENSING.md)
- [Уведомления о сторонних материалах](THIRD_PARTY_NOTICES.md)
- [Развёртывание в Ubuntu](docs/DEPLOYMENT.md)
- [Frontend](frontend/README.md)

### Лицензия

Проект распространяется по [PolyForm Noncommercial License 1.0.0](LICENCE). Коммерческое
использование этой лицензией не разрешается; допустимое некоммерческое использование определяется
текстом лицензии.

Сторонние данные остаются под лицензией, записанной в их source snapshot, и не становятся
PolyForm-материалом из-за включения в приложение.

[К выбору языка](#arduino-component-knowledge-base)
