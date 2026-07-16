# Архитектура

## Принципы

- Backend является единственным источником истины для authorization, validation и state
  transitions; frontend не может повысить права или напрямую менять хранилища.
- PostgreSQL — system of record для предметных данных, job status, media metadata и audit.
- MinIO хранит только binary media; bucket private, доступ выдаётся на короткое время.
- Redis используется как Dramatiq broker, для bounded locks и rate limiting, но не как
  единственное durable хранилище состояния.
- Любое изменение схемы выполняется Alembic migration. Runtime `create_all` запрещён.
- Parser создаёт draft. Duplicate merge требует отдельного решения administrator.

## Контейнеры и ответственность

```text
Browser
  -> reverse-proxy / internal TLS
       -> frontend (React + TypeScript + Vite static build)
       -> backend (FastAPI REST/OpenAPI)
            -> PostgreSQL (data, metadata, jobs, audit)
            -> Redis (Dramatiq broker, locks, rate limits)
            -> MinIO (private binary objects)
       -> worker (Dramatiq actors, parser adapters, Pillow, FFmpeg)
            -> approved HTTPS sources
            -> PostgreSQL / Redis / MinIO
```

`frontend` получает только `/api/v1` contracts и не подключается к PostgreSQL, Redis или
MinIO. `backend` выдаёт presigned media URL лишь после object-level authorization. `worker`
не принимает входящий пользовательский HTTP traffic.

Локальный `compose.yaml` публикует только reverse proxy. PostgreSQL, Redis и MinIO не имеют
host port mappings; migration и media provisioning выполняются одноразовыми jobs до старта
backend/worker. HTTP допустим только для local stage-1 contour. Internal TLS и production
network policy добавляются на этапе корпоративного развёртывания.

## Модули

Frontend организован по маршрутам и server-state boundary:

- `api`: типизированные request/response contracts, same-origin client, CSRF и typed errors;
- `auth`: единственный TanStack Query principal, получаемый из backend `/auth/me`;
- `routing`: React Router tree и UX guards для anonymous/student/administrator;
- `layouts`: student shell и вложенный administrator workspace;
- `pages/components`: route screens и общие loading/error/forbidden states.
- `workspace`: dashboard/list/detail queries и mutations редактора с optimistic revision.

Frontend не принимает authorization decisions: роль из `/auth/me` управляет только
навигацией. Каждый API action и object visibility повторно проверяет backend. Query cache не
является durable state и очищается после logout.

Backend разделяется на API, application services, domain policies и infrastructure adapters.
Направление зависимостей идёт к domain; FastAPI routes не содержат SQL или S3 calls.

- `catalog`: components, categories, tags, revisions, publication;
- реализованный `catalog` хранит mutable editorial head в `components`, а каждое изменение
  фиксирует immutable `component_revisions`; row lock и ожидаемая revision сериализуют mutations;
- reference tables `boards`, `units`, `property_definitions` и `component_properties` задают
  typed technical data без DDL при добавлении новых плат, единиц или свойств;
- `component_compatibility` хранит упорядоченные board/library/platform связи; публикация
  копирует характеристики и совместимость в immutable revision snapshot;
- `identity`: authentication, role assignment и authorization policies;
- `imports`: source policies, URL normalization, jobs и parser results;
- `deduplication`: exact/fuzzy candidates и administrator decisions;
- `media`: upload sessions, metadata, state machine и delivery;
- `audit`: append-only security/business events;
- infrastructure: PostgreSQL repositories, MinIO gateway, Dramatiq actors и HTTP fetcher.

Каждый из `arduino_tex`, `portal_pk` и `alexgyver` — отдельный parser adapter с fixtures,
version и parser-drift error. Общего fallback scraper нет.

Реализованный parser boundary находится в `arduino_component_kb.imports`: `urls` задаёт exact
allowlist и network-address policy, `transport` выполняет DNS validation и pinned HTTPX fetch,
`adapters.base` определяет Protocol и общий безопасный drift diagnostic, а explicit
`arduino_tex`, `portal_pk` и `alexgyver` adapters разбирают свои metadata fixture v1.
`ParsedComponent` не имеет published transition: его единственный status — `draft`.

## Основные потоки

### Локальная authentication и RBAC

1. Backend нормализует login и проверяет durable account/client throttle в PostgreSQL.
2. Argon2id verification использует одинаковый timing path и для неизвестного login.
3. При успехе browser получает opaque `HttpOnly` session cookie и отдельный CSRF cookie;
   PostgreSQL хранит только их SHA-256 hashes, срок действия и признак отзыва.
4. Каждый защищённый запрос заново разрешает active user, session и роли из PostgreSQL.
5. State-changing cookie request проходит double-submit CSRF, затем backend role dependency.
6. Изменение ролей или отключение пользователя отзывает все его сессии и создаёт audit event.
7. Первый administrator создаётся одноразовой интерактивной bootstrap-командой после Alembic.

### Чтение каталога

1. Browser проходит authentication.
2. Backend проверяет `student|teacher|administrator` и status карточки.
3. PostgreSQL возвращает только разрешённую revision; teacher-only fields фильтруются на
   уровне response schema.
   Реализация выбирает последний immutable snapshot со status `published`, исключает archived
   component и применяет bounded search/category/difficulty filters на backend.
4. Для media backend формирует краткоживущий presigned URL после проверки связи asset с
   доступной revision.

### Редактирование карточки

1. Teacher или administrator открывает workspace; student route guard получает deny UX.
2. Frontend загружает категории и текущую draft/revision через TanStack Query.
3. Локальная форма не считается durable state. Preview выводит text/Markdown source без raw
   HTML execution и отдельно маркирует teacher-only notes.
4. Save/publish/archive отправляют CSRF и ожидаемую revision. Backend повторно проверяет роль,
   поля, lifecycle, media и unresolved duplicate candidates.
5. При `revision_conflict` frontend не ретраит mutation, сохраняет локальную форму и предлагает
   пользователю явно загрузить новую серверную revision.
6. Parser по-прежнему может создать только draft; UI не содержит автоматического merge.

### Импорт URL

1. Teacher вызывает `POST /api/v1/import-jobs` с одним URL и idempotency key.
2. Backend проверяет RBAC, HTTPS, allowlisted exact host, source policy, port и canonical URL.
3. В одной PostgreSQL transaction создаётся `import_job=queued`; после commit задача
   публикуется в Dramatiq. Transactional outbox добавляется, если прямую публикацию нельзя
   сделать надёжной на этапе реализации.
4. Worker получает job, ставит bounded Redis lock и выполняет transaction recheck.
5. Safe fetcher резолвит DNS, блокирует non-public IP, pinning connection и повторяет
   validation для каждого redirect. Размер, время и число redirects ограничены.
6. Source adapter извлекает text и media candidates, sanitizes Markdown и возвращает typed
   result. Remote JavaScript, iframe, macro и code не исполняются.
7. Application service сохраняет source record, draft и dedup candidates. Разрешённые
   binary media идут в private quarantine prefix MinIO и отдельные media jobs.
8. Job становится `succeeded`, только когда durable result записан; ошибка сохраняется как
   typed failure и доступна teacher/administrator.

Parser flow реализует URL policy, safe fetch и все три pilot adapters. `DEFAULT_ADAPTERS`
содержит уникальную пару host/parser name и semver parser version; detail URL выбирает ровно
один adapter. Revision `20260716_08` сохраняет durable job, provenance и draft. Exact recheck
выполняется по canonical URL, source item ID и нормализованной manufacturer/model паре.
Revision `20260716_09` запускает bounded fuzzy detector только для нового draft. PostgreSQL
`pg_trgm` ограничивает выборку 50 карточками, затем application scorer `fuzzy-v1` объединяет
token/identity similarity, spec fingerprint, text/media hashes и conflict penalties. Он
записывает только open candidate и evidence; карточки и lifecycle не изменяются.

Revision `20260716_10` добавляет administrator review. API возвращает обе карточки и versioned
score evidence. Команда merge/attach блокирует candidate и обе карточки в стабильном порядке,
повторно проверяет optimistic revisions, переносит provenance/media, архивирует loser и создаёт
immutable decision с before/after snapshot в одной PostgreSQL transaction. Create/reject только
закрывают candidate. Parser и worker не имеют пути к этому transition.

Revision `20260716_11` добавляет `code_examples` и нормализованные ordered hints. Примеры
редактируются вместе с optimistic card revision и входят в immutable published snapshot.
Workspace получает обе visibility, student serializer фильтрует teacher-only записи.
Frontend раскрывает подсказки последовательно и решение по кнопке; tokenizer создаёт только
экранированные React nodes и не является средой исполнения кода.

### Публикация и merge

1. Teacher исправляет draft и запрашивает validation.
2. Backend проверяет обязательные поля, готовность media и unresolved high duplicates.
3. Draft без merge-конфликта может быть опубликован teacher или administrator.
4. Если нужен merge, только administrator выбирает survivor и field-level resolution.
5. PostgreSQL transaction блокирует обе карточки, повторно проверяет revisions, создаёт
   merge decision и audit snapshot, переводит loser в `archived`, затем commit.
6. Никакой worker или parser не вызывает merge transition.

### Upload и обработка медиа

1. Teacher создаёт upload session; backend проверяет quota и возвращает generated object key.
2. Client загружает original в private quarantine через короткий presigned PUT.
3. Backend подтверждает фактический MinIO size, фиксирует durable job в PostgreSQL и после
   commit ставит её в Dramatiq. Если broker временно недоступен, тот же `complete` повторно
   возвращает job UUID и безопасно повторяет доставку.
4. Worker проверяет size, MIME/magic bytes, декодирует с resource limits, создаёт variants
   и сохраняет hashes/metadata в PostgreSQL; image pipeline не увеличивает originals.
   Video worker выполняет bounded `ffprobe`, локальный H.264/AAC transcode и WebP poster,
   повторно проверяет rendition и сохраняет coarse-grained phase/progress после этапов.
5. Asset становится `ready` либо `rejected`; completion атомарно фиксирует progress `100`,
   partial objects удаляются retention job.

## Согласованность и отказоустойчивость

- PostgreSQL constraints и transaction recheck обеспечивают correctness; Redis lock снижает
  конкуренцию, но его потеря не нарушает инварианты.
- Dramatiq actors idempotent по job UUID и повторно читают durable state.
- Retry разрешён только для transient failures с exponential backoff и max attempts.
  Validation, authorization, parser drift и quota failures не ретраятся автоматически.
- Claim выполняется под PostgreSQL row lock. Активный `running` heartbeat образует lease;
  повторная доставка пропускается, а просроченная lease может быть безопасно перехвачена.
- `queued → running → retrying → running` повторяется в пределах `max_attempts`; terminal
  result — только `succeeded` или `failed`. Dramatiq retry delay и `next_retry_at` фиксируются
  согласованно. Очистка Redis не переписывает durable status.
- Administrator monitor читает PostgreSQL с фильтрами и polling. Ручной retry разрешён только
  для `failed` (повторный запрос к уже `queued` лишь повторяет доставку) и записывается в audit.
- Object upload и DB commit не атомарны: orphan/pending objects убирает audited retention job.
- Ошибки внешнего источника не меняют уже published component и не скрываются.

## Deployment boundaries

Reverse proxy — единственная опубликованная точка входа. PostgreSQL, Redis, MinIO admin API
и worker остаются во внутренней container network. Internal TLS, firewall, backups,
monitoring и restore drill обязательны перед production. Production credentials поступают
через secrets/environment mechanism и не хранятся в Git.

## Решения, отложенные до следующих этапов

Локальные opaque server-side sessions утверждены как MVP baseline. Возможная интеграция с
колледжным SSO не должна менять backend RBAC, отзыв сессий и audit invariants. Outbox
implementation, merge/review UI, backup tooling и orchestrator остаются отложенными.

## Поиск опубликованного каталога

PostgreSQL обслуживает поиск без отдельного search engine. При публикации backend в той же
транзакции обновляет `published_search_documents` из immutable published snapshot; archive
удаляет документ. В индекс входят только title, aliases, manufacturer, model, summary и tags.
Draft content, teacher notes, solutions и code examples не индексируются.

Основной путь использует weighted `tsvector` и `plainto_tsquery('simple', ...)`: identity-поля
получают больший вес, чем summary/tags. `pg_trgm` word similarity является fallback для
опечаток. Category/difficulty predicates, ranking, ordering и limit выполняются SQL. GIN
индексы покрывают FTS и trigram, B-tree — category/difficulty. Диагностический
`ackb-explain-search` запускает параметризованный `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`
в read-only transaction на явном operator query.
