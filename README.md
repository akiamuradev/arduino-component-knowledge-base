# Arduino Component Knowledge Base

Внутренняя образовательная web-платформа колледжа для ведения каталога
Arduino-совместимых компонентов. Требования этапа 0 утверждены; текущая реализация содержит
инфраструктурное ядро FastAPI, async PostgreSQL integration, локальную аутентификацию и
backend RBAC.

Проект распространяется по [PolyForm Noncommercial License 1.0.0](LICENCE). Коммерческое
использование этой лицензией не разрешается; образовательное использование колледжем входит
в определённые лицензией noncommercial purposes.

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
- [Модель угроз](docs/THREAT_MODEL.md)
- [Автоматизированное тестирование](docs/TESTING.md)
- [Корпоративное развёртывание](docs/DEPLOYMENT.md)

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

## Каталог и CRUD

- Alembic revision `20260716_06` создаёт категории, карточки, immutable revisions, aliases,
  tags, boards, units и typed property definitions/values; revision `20260716_07` добавляет
  структурированную совместимость карточек;
- десять утверждённых baseline-категорий являются данными PostgreSQL, а не frontend-константами;
- teacher и administrator работают через `/api/v1/workspace/*`; student получает backend deny;
- save, publish и archive выполняются под row lock и требуют актуальную `revision`;
  устаревшая запись получает `409 revision_conflict`;
- изменение опубликованной карточки создаёт новый draft, а опубликованный snapshot остаётся
  immutable; публикация требует ручного оригинала до подключения source persistence;
- только administrator создаёт и деактивирует категории, причём используемая категория или
  категория с активными дочерними элементами не деактивируется;
- parser boundary по-прежнему создаёт только `draft` и не получил publish/merge полномочий.

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
- student catalog получает реальные published snapshots через `/api/v1/catalog/*`, поддерживает
  bounded поиск, категории и сложность, а detail page не получает teacher-only поля;
- характеристики и совместимость редактируются в workspace и читаются student только из
  последнего published snapshot;
- loading, error и empty states не подменяют backend фиктивными данными.
- light/dark/system темы применяются до старта React и хранят только визуальное предпочтение;
- product identity `akiamuradev`, build metadata и фактическая PolyForm Noncommercial License
  централизованы во frontend и отображаются в footer, login и `/about`;
- интерактивный login OLED является только доступным визуальным feedback реального auth flow и
  не определяет credentials, роли или permissions;
- media/provenance UI использует optional typed contracts и ничего не показывает без metadata
  backend; агрегированный `/sources` отложен до появления соответствующего endpoint.

## Redis и фоновые задачи

- Dramatiq использует отдельные Redis queues `images`, `videos` и `imports`; PostgreSQL остаётся durable
  источником job status и хранит idempotency key, attempts, heartbeat, retry deadline и progress;
- actors получают job UUID, claim выполняется под row lock и lease, поэтому повторная доставка
  не запускает завершённую или уже выполняющуюся задачу;
- transient MinIO failures переходят в `retrying` с bounded exponential backoff, а validation
  failures и исчерпанные попытки — в `failed` с безопасным typed code;
- `/admin/jobs` доступен только administrator, обновляется через TanStack Query polling и
  позволяет audited CSRF-protected retry failed job;
- parser использует durable `import_jobs`, bounded Redis lock и PostgreSQL transaction recheck,
  создаёт только draft, а duplicate merge остаётся отдельным подтверждением administrator.

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

Revision `20260716_08` добавляет `sources`, `component_sources`, `import_jobs` и exact UNIQUE
ключи. Teacher/administrator запускает импорт через `POST /api/v1/import-jobs`; повторный
exact import возвращает существующий component ID и не создаёт вторую карточку.

Revision `20260716_09` включает PostgreSQL `pg_trgm`, GIN preselection indexes и
`duplicate_candidates`. Для каждого нового import draft bounded detector `fuzzy-v1` считает
title trigram, token/identity similarity, fingerprint характеристик, text/media hashes и
явные conflict penalties. Candidate сохраняется с versioned evidence; detector не выполняет
merge, attach, reject или publication.

Revision `20260716_10` добавляет admin-only очередь `/admin/duplicates`: две карточки, score
breakdown, совпадения/конфликты и явные действия merge/attach/create/reject. Backend повторно
проверяет обе revision и сохраняет immutable decision, audit и snapshots в одной транзакции.

## Рабочее место преподавателя

- dashboard показывает реальные backend counts и последние карточки;
- редактор покрывает утверждённые идентификационные и учебные поля карточки;
- preview выводит пользовательский текст как React text nodes и не исполняет raw HTML;
- сохранение, publish и archive передают текущую optimistic `revision`;
- `409 revision_conflict` останавливает запись, сохраняет локальную форму и предлагает явно
  загрузить серверную revision;
- student не получает editorial routes, teacher и administrator получают их только после
  `/auth/me`.

Frontend-контракты `/api/v1/workspace/*` и `/api/v1/catalog/*` реализованы backend. Workspace
доступен teacher/administrator, а student API возвращает только последний published snapshot.

Подробности и команды находятся в [frontend README](frontend/README.md).

## Учебные примеры кода

Revision `20260716_11` добавляет practical tasks, ordered hints, libraries, explanation и
решение до 64 KiB. Student раскрывает подсказки по порядку и решение отдельным действием;
teacher-only примеры backend не включает в student API. Подсветка синтаксиса работает на
экранированных React text nodes, backend и worker никогда не исполняют код.

## Локальный запуск

Требуются Python 3.12+, отдельная PostgreSQL database, Redis, MinIO, `ffprobe` и `ffmpeg`
с поддержкой `libx264`, AAC и WebP. Не используйте production или чужие ресурсы для разработки.

### Docker Compose

Воспроизводимый локальный контур включает PostgreSQL, Redis, MinIO, одноразовые Alembic и
bucket-provisioning jobs, FastAPI backend, раздельные Dramatiq media/parser workers, React
static frontend и reverse proxy. Наружу публикуется только `${ACKB_HTTP_PORT:-8080}`;
`edge`/`data` изолированы, внешний egress есть только у parser worker.

```bash
cp .env.example .env
# заменить все replace-with-* только в локальном .env
docker compose up --build -d
python scripts/compose_smoke.py
docker compose down
```

Первый запуск применяет только существующие Alembic migrations и создаёт private MinIO
buckets. Application startup не выполняет DDL. Для bootstrap administrator после healthy
старта используется отдельная интерактивная команда:

```bash
docker compose run --rm backend ackb-bootstrap-admin \
  --login admin --display-name "Initial Administrator"
```

Локальный Compose использует HTTP и общие локальные MinIO credentials из `.env`. Production
override, internal HTTPS, static IP/DNS и firewall описаны отдельно в
[корпоративном runbook](docs/DEPLOYMENT.md); они не имитируются в локальном контуре.

### Корпоративная Ubuntu Server VM

Этап 20 добавляет `compose.production.yaml`, nginx TLS template, read-only preflight и HTTPS
smoke. Production публикует только заданный static IP на портах 80/443, включает secure session
cookies, TLS для MinIO и CA bundle без отключения certificate verification. Реальные IP, DNS,
сертификаты внутреннего CA и firewall CIDR выбирает администратор колледжа и не хранит в Git.

```bash
cp .env.production.example .env.production
chmod 600 .env.production
./scripts/production_preflight.sh .env.production
docker compose --env-file .env.production \
  -f compose.yaml -f compose.production.yaml up --build -d
ACKB_SMOKE_BASE_URL=https://components.college.internal/ \
ACKB_SMOKE_CA_FILE=/etc/ackb/tls/ca-bundle.crt \
python scripts/production_smoke.py
```

### Чистая Linux VM

Для Ubuntu/Debian VM установите Docker Engine по
[официальной инструкции](https://docs.docker.com/engine/install/ubuntu/) и
[Compose plugin](https://docs.docker.com/compose/install/linux/), а также host-команды `curl` и
`openssl`. Не используйте устаревший standalone `docker-compose`.

```bash
git clone <repository-url> arduino-component-knowledge-base
cd arduino-component-knowledge-base
./scripts/linux_bootstrap.sh
```

Скрипт проверяет доступ к daemon, создаёт ignored `.env` с mode `0600` и случайными local
credentials, не выводит их, выполняет `docker compose config`, собирает stack и ждёт
frontend, `/health` и `/ready`. Повторный запуск сохраняет существующий `.env`; наличие
placeholder останавливает запуск с явной ошибкой.

Управление после запуска:

```bash
docker compose ps
docker compose logs -f backend worker parser-worker
docker compose down
# удалить также локальные данные только при осознанном полном сбросе:
docker compose down --volumes
```

### Запуск без контейнеров

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
dramatiq arduino_component_kb.worker
```

Compose разделяет очереди: media worker обслуживает `images/videos` без внешнего egress,
parser worker — только `imports` с отдельной egress network.

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
| `POST` | `/api/v1/import-jobs` | Teacher/admin URL import с обязательным idempotency key |
| `GET` | `/api/v1/import-jobs/{id}` | Статус собственного import job; administrator видит любой |

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
python scripts/dedup_smoke.py
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
воспроизводимый Docker Compose/CI каркас, authentication/RBAC, frontend-каркас, безопасные image/video pipelines, durable
Redis/Dramatiq jobs и SSRF-safe parser boundary с тремя pilot adapters.
Предметные таблицы каталога, workspace/student API и durable exact import реализованы.
Fuzzy detector `fuzzy-v1` создаёт объяснимые candidates, не изменяя карточки. Экран
администратора фиксирует merge/attach/create/reject только после просмотра evidence.
Учебный блок хранит practical tasks, ordered hints, libraries, explanations и скрываемые
решения в published revision; teacher-only примеры не выдаются student API.
Каталог использует PostgreSQL weighted full-text search по опубликованным title, aliases,
manufacturer/model, summary и tags, а `pg_trgm` исправляет опечатки; category/difficulty
фильтруются SQL. Revision `20260716_12` хранит отдельный published-only search document.
План запроса на живом PostgreSQL проверяется командой
`ackb-explain-search --query "Arduino Uno"` из backend environment.
Security baseline закрывает RBAC/IDOR, CSRF/same-origin/CSP, adversarial parser/upload cases и
разделяет internal data/media networks с единственным parser egress. Исполняемая модель угроз
зафиксирована в [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
Открытые продуктовые вопросы перечислены в конце
[требований](docs/REQUIREMENTS.md#открытые-вопросы-перед-production-импортом).
