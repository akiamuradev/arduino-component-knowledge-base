# Arduino Component Knowledge Base

Внутренняя образовательная web-платформа колледжа для ведения каталога
Arduino-совместимых компонентов. Требования этапа 0 утверждены; текущая реализация содержит
инфраструктурное ядро FastAPI, async PostgreSQL integration, локальную аутентификацию и
backend RBAC.

## Утверждённые пилотные источники

1. <https://arduino-tex.ru/>
2. <https://portal-pk.ru/>
3. <https://alexgyver.ru/ardu-proj/>

URL проверены как доступные тематические страницы 15 июля 2026 года. Они являются
пилотными входными точками, но не разрешением на копирование материалов. До включения
скачивания текста или медиа администратор обязан зафиксировать разрешённый объём импорта,
условия использования и атрибуцию для каждого источника.

## Документы

- [Требования](docs/REQUIREMENTS.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [Модель данных](docs/DATA_MODEL.md)
- [Безопасность](docs/SECURITY.md)

Вместе эти документы утверждают роли, карточку компонента, категории, медиа-лимиты,
потоки импорта и дедупликации, а также обязательные security controls.

## Зафиксированный стек

- frontend: React, TypeScript и Vite;
- backend: FastAPI, Pydantic, SQLAlchemy 2 и PostgreSQL;
- binary media: private buckets в MinIO, metadata — только в PostgreSQL;
- фоновые задачи: Redis и Dramatiq;
- изменение схемы: только Alembic;
- развёртывание: Docker Compose за reverse proxy.

## Backend-инфраструктура

- `create_app()` создаёт изолированный FastAPI instance и управляет database lifecycle;
- `Settings` принимает только `ACKB_*` environment variables и валидирует
  `postgresql+asyncpg` URL;
- SQLAlchemy 2 использует async engine, asyncpg, bounded pool и `pool_pre_ping`;
- `/health` проверяет процесс без обращения к БД;
- `/ready` выполняет `SELECT 1` и возвращает `503`, если PostgreSQL недоступен;
- JSON logging использует безопасные bounded fields и `X-Request-ID`;
- Alembic — единственный DDL mechanism; startup не создаёт и не мигрирует таблицы.

## Authentication и RBAC

- локальные пароли хэшируются Argon2id; публичной регистрации нет;
- browser получает opaque server-side session в `HttpOnly` cookie, а PostgreSQL хранит
  только SHA-256 hash session/CSRF material;
- изменяющие запросы требуют double-submit `ackb_csrf` cookie и `X-CSRF-Token` header;
- роли `student`, `teacher`, `administrator` проверяются backend dependencies;
- только administrator создаёт пользователей, заменяет роли и отключает аккаунты;
- роль последнего активного administrator нельзя снять, его аккаунт нельзя отключить;
- login failures ограничиваются долговечными account/client counters в PostgreSQL;
- login/logout и административные изменения создают audit events без паролей, raw tokens,
  логинов клиентов и IP-адресов.

Interactive Swagger UI выключен по умолчанию. OpenAPI доступен по
`/api/v1/openapi.json`; для локальной разработки `/docs` включается явным
`ACKB_DOCS_ENABLED=true`.

## MinIO и изображения

- teacher/administrator резервирует upload через backend; server-generated key указывает в
  отдельный private quarantine bucket и выдаётся как presigned PUT не дольше 15 минут;
- подтверждение сверяет фактический размер MinIO object, создаёт durable PostgreSQL job и
  отправляет её в очередь Dramatiq через Redis; повторное подтверждение идемпотентно;
- worker независимо от filename и клиентского Content-Type проверяет размер, MIME, magic bytes,
  логический конец контейнера, полное декодирование Pillow, отсутствие анимации и лимиты
  20 MP/10 000 px;
- безопасный re-encode удаляет metadata и создаёт WebP `320w`, `800w`, `1600w` без увеличения;
  PostgreSQL хранит только metadata, SHA-256 и 64-bit pHash, binary остаётся в MinIO;
- bucket provisioning вынесен в `ackb-provision-media` и завершается ошибкой, если обнаружена
  bucket policy: baseline требует private-by-default buckets.

## Локальное видео и FFmpeg

- teacher/administrator загружает MP4, MOV или WebM до 256 MiB тем же private quarantine
  flow; source object никогда не выдаётся студенту;
- worker запускает `ffprobe` и `ffmpeg` напрямую без shell, с отдельными configurable paths,
  timeout и ограниченным числом threads;
- вход проверяется по magic/container, размеру, единственному video stream, продолжительности
  до 10 минут, разрешению до 1920×1080 и frame rate до 30 fps;
- создаются metadata-free MP4 rendition H.264/AAC до 1280×720 и WebP poster; оба результата
  повторно валидируются до перехода asset в `ready`;
- PostgreSQL хранит codec/duration/frame-rate, job phase и progress `0..100`; binary rendition
  и poster находятся только в private MinIO variants bucket.

## Frontend-каркас

- React Router разделяет login, student catalog и editorial workspace для teacher/administrator;
- TanStack Query владеет server state и повторно получает principal через `/auth/me`;
- typed API client отправляет opaque cookies, добавляет CSRF header к mutations и сохраняет
  backend status/error code;
- route guards скрывают недоступный UX, но не считаются authorization control;
- loading, recoverable error, forbidden и not-found состояния заданы явно;
- frontend не имитирует ещё не реализованный catalog/admin API фиктивными данными.

## Redis и фоновые задачи

- Dramatiq использует отдельные Redis queues `images` и `videos`; PostgreSQL остаётся durable
  источником job status и хранит idempotency key, attempts, heartbeat, retry deadline и progress;
- actors получают job UUID, claim выполняется под row lock и lease, поэтому повторная доставка
  не запускает завершённую или уже выполняющуюся задачу;
- transient MinIO failures переходят в `retrying` с bounded exponential backoff, а validation
  failures и исчерпанные попытки — в `failed` с безопасным typed code;
- `/admin/jobs` доступен только administrator, обновляется через TanStack Query polling и
  позволяет audited CSRF-protected retry failed job;
- будущий parser должен использовать тот же durable contract и по-прежнему создавать только
  draft, а duplicate merge остаётся отдельным подтверждением administrator.

## Парсеры пилотных источников

- три versioned adapters обрабатывают `arduino-tex.ru/news/{id}/{slug}.html`,
  `portal-pk.ru/news/{id}-{slug}.html` и detail pages `alexgyver.ru/{project}/`;
  pilot fixtures v1 закрепляют DOM-контракты KY-023, keypad 4x4 и MIDI stepper;
- общий allowlist содержит только exact hosts `arduino-tex.ru`, `portal-pk.ru` и
  `alexgyver.ru`; для каждого host зарегистрирован отдельный adapter, общего fallback scraper нет;
- HTTPX transport запрещает HTTP, userinfo, нестандартные порты и неразрешённые hosts,
  проверяет все DNS A/AAAA, блокирует non-global ranges и подключается к проверенному IP с
  исходными Host/SNI и TLS verification;
- каждый redirect заново проходит URL/DNS/IP policy; proxy/cookies отключены, HTML ограничен
  тремя redirects, 32 KiB headers, 2 MiB decoded body и общим timeout;
- adapter сохраняет только bounded title/description metadata и provenance. Remote body,
  scripts, links и media не переносятся; `ParsedComponent.status` конструктивно равен `draft`,
  а source policy — `metadata_only`.
- drift diagnostics содержат только typed code, source host, parser name/version и имя поля;
  remote HTML и exception details в диагностику не включаются.

На этом этапе parser boundary не создаёт PostgreSQL records и не публикует Dramatiq job.
Durable `import_jobs`, catalog draft persistence и API требуют следующей Alembic migration.

## Рабочее место преподавателя

- dashboard показывает реальные backend counts и последние карточки;
- редактор покрывает утверждённые идентификационные и учебные поля карточки;
- preview выводит пользовательский текст как React text nodes и не исполняет raw HTML;
- сохранение, publish и archive передают текущую optimistic `revision`;
- `409 revision_conflict` останавливает запись, сохраняет локальную форму и предлагает явно
  загрузить серверную revision;
- student не получает editorial routes, teacher и administrator получают их только после
  `/auth/me`.

Frontend-контракт ожидает `/api/v1/workspace/*`. Эти endpoints и предметная PostgreSQL-схема
пока не реализованы: интерфейс показывает backend error и не подменяет его фиктивным успехом.

Подробности и команды находятся в [frontend README](frontend/README.md).

## Локальный запуск

Требуются Python 3.12+, отдельная PostgreSQL database, Redis, MinIO, `ffprobe` и `ffmpeg`
с поддержкой `libx264`, AAC и WebP. Не используйте production или чужие ресурсы для разработки.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
ackb-provision-media
ackb-bootstrap-admin --login admin --display-name "Initial Administrator"
uvicorn arduino_component_kb.main:create_app --factory
```

Worker запускается отдельным процессом после применения миграций и provisioning buckets:

```bash
dramatiq arduino_component_kb.media.tasks
```

Во втором терминале:

```bash
cd frontend
npm ci
npm run dev
```

В PowerShell вместо `cp`:

```powershell
Copy-Item .env.example .env
```

Перед запуском замените placeholder database password и
`ACKB_AUTH_THROTTLE_PEPPER` на отдельную случайную строку длиной не менее 32 символов в
локальном `.env`. Файл `.env`
игнорируется Git. Приложение намеренно завершит создание, если `ACKB_DATABASE_URL`
отсутствует или использует не `postgresql+asyncpg`.

Bootstrap-команда читает пароль дважды через TTY и не принимает его аргументом командной
строки. Она работает только пока в базе нет активного administrator.

## HTTP contracts

| Метод | Endpoint | Назначение |
|---|---|---|
| `GET` | `/health` | Liveness процесса; не зависит от PostgreSQL |
| `GET` | `/ready` | Readiness с bounded PostgreSQL probe |
| `GET` | `/api/v1/openapi.json` | Versioned OpenAPI contract |
| `POST` | `/api/v1/auth/login` | Локальный login и выдача opaque session cookies |
| `GET` | `/api/v1/auth/me` | Principal, заново разрешённый backend из сессии |
| `POST` | `/api/v1/auth/logout` | CSRF-protected отзыв текущей сессии |
| `POST` | `/api/v1/admin/users` | Administrator-only создание пользователя |
| `PUT` | `/api/v1/admin/users/{id}/roles` | Administrator-only замена ролей |
| `POST` | `/api/v1/admin/users/{id}/disable` | Administrator-only отключение аккаунта |
| `POST` | `/api/v1/media/images/uploads` | Teacher/admin reservation и presigned PUT |
| `POST` | `/api/v1/media/images/{id}/complete` | CSRF-protected подтверждение и постановка image job |
| `GET` | `/api/v1/media/images/{id}` | Owner/admin metadata и processing status |
| `POST` | `/api/v1/media/videos/uploads` | Teacher/admin video reservation и presigned PUT |
| `POST` | `/api/v1/media/videos/{id}/complete` | Подтверждение и постановка video job |
| `GET` | `/api/v1/media/videos/{id}` | Owner/admin metadata, phase и progress |
| `GET` | `/api/v1/admin/jobs` | Administrator-only monitor durable jobs |
| `POST` | `/api/v1/admin/jobs/{id}/retry` | Audited CSRF-protected ручной retry failed job |

`/ready` возвращает `200` и `ready` только после успешного `SELECT 1`; dependency failure
возвращает `503` и безопасный `not_ready`, а не ложный success.

## Проверки

После установки Python 3.12+:

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
python scripts/auth_smoke.py
python scripts/media_smoke.py
python scripts/video_smoke.py
python scripts/jobs_smoke.py
python scripts/parser_smoke.py
alembic upgrade head --sql
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
npm run smoke
```

`backend_smoke.py` проверяет HTTP application factory с dependency-isolated database
gateway. Offline Alembic smoke компилирует PostgreSQL DDL, но не доказывает доступность
реального PostgreSQL; для этого нужен отдельный integration environment.

## Статус решений

Утверждены продуктовые и архитектурные defaults этапа 0, созданы backend-ядро,
authentication/RBAC, frontend-каркас, безопасные image/video pipelines, durable
Redis/Dramatiq jobs и SSRF-safe parser boundary с тремя pilot adapters.
Предметные таблицы каталога и durable import orchestration ещё не реализованы. Editorial UI
подготовлен, но требует workspace API следующего backend-этапа.
Открытые продуктовые вопросы перечислены в конце
[требований](docs/REQUIREMENTS.md#открытые-вопросы-перед-production-импортом).
