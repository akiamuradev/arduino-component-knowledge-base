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
       -> media worker (Dramatiq images/videos, Pillow, FFmpeg; no external egress)
            -> PostgreSQL / Redis / MinIO
       -> parser worker (Dramatiq imports; dedicated egress)
            -> approved HTTPS sources
            -> PostgreSQL / Redis
```

`frontend` получает только `/api/v1` contracts и не подключается к PostgreSQL, Redis или
MinIO. `backend` выдаёт presigned media URL лишь после object-level authorization. `worker`
не принимает входящий пользовательский HTTP traffic.

Локальный `compose.yaml` публикует только reverse proxy. PostgreSQL, Redis и MinIO не имеют
host port mappings; migration и media provisioning выполняются одноразовыми jobs до старта
backend/worker. HTTP допустим только для local stage-1 contour. `compose.production.yaml`
публикует заданный static IP только на 80/443, включает edge и MinIO TLS, secure cookies и
read-only CA bundle. Сети `edge`/`data` остаются internal, reverse proxy дополнительно подключён
к host-facing `ingress`, а `parser-egress` отделён. Реальные
static IP, internal DNS, CA trust и host/perimeter firewall проверяются по deployment runbook.

## Модули

Frontend организован по маршрутам и server-state boundary:

- `api`: типизированные request/response contracts, same-origin client, CSRF и typed errors;
- `auth`: единственный TanStack Query principal, получаемый из backend `/auth/me`;
- `routing`: React Router tree и UX guards по серверным permissions;
- `theme` и `config`: light/dark/system preference, неизменяемая product identity и безопасные
  build metadata без auth/session данных;
- `components`: общий header/footer, OLED login feedback, catalog cards и optional
  media/provenance presentation; эти компоненты не расширяют backend permissions;
- `layouts`: student shell и вложенный administrator workspace;
- `pages/components`: route screens и общие loading/error/forbidden states.
- `workspace`: dashboard/list/detail queries и mutations редактора с optimistic revision.
- `audit`: read-only administrator query и русский экран с user/action/date filters.

Frontend не принимает authorization decisions: permissions из `/auth/me` управляют только
навигацией и доступностью действий. Роли используются для отображаемого названия профиля.
Каждый API action и object visibility повторно проверяет backend. Query cache не является
durable state и очищается после logout.

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

Исторические `arduino_tex`, `portal_pk` и `alexgyver` сохранены как отдельные fixture-driven
adapters для audit compatibility, но database policy запрещает новые jobs. Активные
`seeed-wiki-git-v1` и `kicad-symbols-v1` реализуют отдельный repository contract. Общего
fallback scraper нет.

Реализованный parser boundary находится в `arduino_component_kb.imports`: `urls` задаёт exact
историческую allowlist и network-address policy, `transport` выполняет DNS validation и pinned HTTPX fetch,
`adapters.base` определяет Protocol и общий безопасный drift diagnostic, а explicit
`arduino_tex`, `portal_pk` и `alexgyver` adapters разбирают свои metadata fixture v1.
`ParsedComponent` и `ParsedRepositoryComponent` не имеют published transition: результат
может быть только draft.

## Основные потоки

### Локальная authentication и RBAC

1. Backend нормализует login и проверяет durable account/client throttle в PostgreSQL.
2. Argon2id verification использует одинаковый timing path и для неизвестного login.
3. При успехе browser получает opaque `HttpOnly` session cookie и отдельный CSRF cookie;
   PostgreSQL хранит только их SHA-256 hashes, срок действия и признак отзыва.
4. Login schema принимает только login/password и отклоняет клиентские role/permissions.
   `/auth/login` и `/auth/me` возвращают минимальную identity вместе с вычисленными сервером
   roles и permissions.
5. Каждый защищённый запрос заново разрешает active user, session и непросроченные,
   неотозванные role grants из PostgreSQL.
6. Централизованная таблица соответствия ролей и permissions формирует capabilities
   principal; route dependency проверяет permissions, а не данные клиента.
7. State-changing cookie request проходит double-submit CSRF, затем backend permission
   dependency.
8. Изменение ролей или отключение пользователя отзывает все его сессии и создаёт audit event.
   Истёкший `editor` автоматически теряет редакторские permissions без удаления grant history.
9. `/admin/users` получает безопасный список accounts без password hashes. Узкие create/grant
   editor inputs принимают срок, но не роль: временный редактор создаётся с постоянным
   `student`, grant/early revoke не заменяют базовые роли и сохраняют прошлые строки grants.
10. Первый administrator создаётся одноразовой интерактивной bootstrap-командой после Alembic.

### Журнал действий

1. Серверные authentication, identity, catalog, import, media, retention и settings операции
   добавляют bounded event через общий `AuthRepository.audit`; allowlist метаданных не принимает
   произвольные поля или вложенные payload.
2. PostgreSQL хранит append-only event с UTC-временем, actor, action, object и outcome.
   Индексы `actor_user_id+occurred_at` и `action+occurred_at` обслуживают точные фильтры.
3. `GET /api/v1/admin/audit-events` требует `audit.view`, ограничивает limit/offset и возвращает
   отдельную safe projection без details/request ID с `Cache-Control: no-store`.
4. `/admin/audit` показывает русские actor/action/object/outcome labels. UI не содержит
   mutation controls; student, teacher и editor получают backend deny независимо от route guard.

### Чтение каталога

1. Browser проходит authentication.
2. Backend требует `components.view`; это разрешение есть у всех четырёх человеческих ролей.
3. PostgreSQL возвращает только разрешённую revision; teacher-only fields фильтруются на
   уровне response schema.
   Реализация выбирает последний immutable snapshot со status `published`, исключает archived
   component и применяет bounded search/category/difficulty filters на backend.
4. Для media backend формирует краткоживущий presigned URL после проверки связи asset с
   доступной revision.

### Редактирование карточки

1. Editor или administrator открывает workspace; student/teacher получают backend deny,
   независимо от frontend route guard.
2. Frontend загружает категории и текущую draft/revision через TanStack Query.
3. Локальная форма не считается durable state. Preview выводит text/Markdown source без raw
   HTML execution и отдельно маркирует teacher-only notes.
4. Save и каждый lifecycle action отправляют CSRF и ожидаемую revision. Backend отдельно
   требует `components.edit`, `components.submit_for_review`, `components.review`,
   `components.publish` или `components.archive`, затем проверяет permission, допустимую
   исходную state, поля, media и unresolved duplicate candidates.
5. При `revision_conflict` frontend не ретраит mutation, сохраняет локальную форму и предлагает
   пользователю явно загрузить новую серверную revision.
6. Editor редактирует `draft`/`changes_requested`, отправляет карточку в `in_review`;
   administrator возвращает изменения или переводит её в `approved`, затем явно публикует.
   `hidden` выключает публичную выдачу без потери snapshot. `archived` сохраняет исходный статус
   для обратимого restore; физического удаления через HTTP нет.
7. Редактирование published head переводит её в `draft`, но student API продолжает читать
   предыдущий immutable published snapshot до следующего review/publish.
8. Каждое изменение создаёт immutable revision с actor, временем, server action, предыдущим и
   новым статусом и коротким описанием. Тот же набор безопасных полей записывается в audit.
   Вкладка «История» не читает snapshot payload: editor получает только свои карточки,
   administrator — все.
9. Parser по-прежнему может создать только draft; UI не содержит автоматического merge.

### Предложение исправления

1. Teacher читает immutable published projection и отправляет plain-text замечание длиной
   10–4000 символов. Endpoint требует отдельное `components.propose_correction` и CSRF.
2. PostgreSQL сохраняет замечание отдельно от карточки со статусом `open`; опубликованная и
   рабочая revisions не изменяются.
3. Автор карточки с `components.edit` либо administrator видит предложение во вкладке
   «Предложения» и однократно переводит его в `applied` или `dismissed`.
4. Создание и решение фиксируются в audit; student не видит форму, teacher не получает
   workspace, а прямой вызов editor API остаётся `403`.

### Импорт URL

1. Editor или administrator вызывает `POST /api/v1/import-jobs` с одним URL и idempotency key.
2. Backend проверяет `imports.create`, HTTPS, allowlisted exact host, source policy, port и
   canonical URL.
3. В одной PostgreSQL transaction создаются `import_job=queued` и bounded
   `job_dispatch=pending`. Отдельный `job-reconciler` публикует opaque job UUID в Dramatiq и
   отмечает доставку в PostgreSQL; browser request не зависит от доступности Redis.
4. Worker получает job, ставит bounded Redis lock и выполняет transaction recheck.
5. Safe fetcher резолвит DNS, блокирует non-public IP, pinning connection и повторяет
   validation для каждого redirect. Размер, время и число redirects ограничены.
6. Source adapter извлекает text и media candidates, sanitizes Markdown и возвращает typed
   result. Remote JavaScript, iframe, macro и code не исполняются.
7. Application service сохраняет source record, draft и dedup candidates. Разрешённые
   binary media идут в private quarantine prefix MinIO и отдельные media jobs.
8. Job становится `succeeded`, только когда durable result записан; ошибка сохраняется как
   typed failure и доступна owner-editor/administrator.

### Пользовательская страница загрузок

`GET /api/v1/import-jobs` формирует отдельную безопасную read model: название, зарегистрированный
источник, автор, дата, понятное состояние, результат и доступные действия. Editor получает только
свои операции, administrator — все. Технические поля durable job не входят в этот response и
остаются в `GET /api/v1/admin/jobs/imports` под `system.diagnostics`.

`POST /api/v1/import-jobs/{id}/retry` и `/cancel` проверяют capability и ownership на сервере.
Отмена фиксируется в PostgreSQL как terminal `cancelled`; worker проверяет это состояние перед
началом и перед сохранением результата.

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

Изображения карточки используют существующие `media_assets`/`media_variants`. Component row lock
сериализует attach, reorder, primary и detach; БД гарантирует at-most-one primary, а publication
service — непустую ready-коллекцию и exactly-one primary. Published API читает порядок и metadata
из immutable `component_revisions.content_json.media`, проверяя variant по asset ID и SHA-256;
bucket, object key и original никогда не входят в snapshot.
Workspace получает обе visibility, student serializer фильтрует teacher-only записи.
Frontend раскрывает подсказки последовательно и решение по кнопке; tokenizer создаёт только
экранированные React nodes и не является средой исполнения кода.

### Импорт registered Git repositories

Revision `20260716_13` оставляет прежнюю HTML boundary только для чтения исторических fixtures,
но деактивирует три website source в PostgreSQL. API и worker повторно требуют `status=active`,
`is_enabled=true`, `permission_status=license_granted`; поэтому ранее поставленный denied job
завершается `source_disabled` до network access.

Новый `RepositorySourceAdapter` не является расширением URL scraper. Его единица работы —
registered repository, полный immutable commit SHA, безопасный POSIX file path и optional entry
name. `RepositorySnapshot` проверяет repository identity, SHA, file count, file size и path
containment. Получение archive/shallow snapshot и разрешение tag/branch выполняются отдельным
infrastructure boundary этапа VM validation; adapter получает только уже фиксированный snapshot.

`seeed-wiki-git-v1` разделён на document loading, bounded frontmatter, section detection,
table parsing, unit normalization, mapping и provenance. MDX/JSX/import/export/code fences
удаляются как данные без исполнения. `kicad-symbols-v1` использует собственный bounded
S-expression reader, configurable backend library allowlist и не вызывает KiCad или shell.

Оба adapter возвращают `ParsedRepositoryComponent`: typed status/warnings, normalized fields,
field-level provenance, license snapshot, attribution и modifications notice. Persistence key
включает source, normalized repository, commit, file и KiCad symbol name. Та же revision
переиспользует результат; новая revision создаёт отдельный draft/review candidate и не изменяет
published snapshot. На publication backend копирует source/license data в immutable
`component_revisions.content_json` и возвращает отдельный typed code для каждого отсутствующего
обязательного элемента.

### Публикация и merge

1. Editor исправляет draft и отправляет его на проверку.
2. Backend проверяет обязательные поля, готовность media и unresolved high duplicates.
3. Draft без merge-конфликта может быть опубликован только administrator.
4. Если нужен merge, только administrator выбирает survivor и field-level resolution.
5. PostgreSQL transaction блокирует обе карточки, повторно проверяет revisions, создаёт
   merge decision и audit snapshot, переводит loser в `archived`, затем commit.
6. Никакой worker или parser не вызывает merge transition.

### Upload и обработка медиа

1. Editor создаёт upload session; backend проверяет quota и возвращает generated object key.
2. Client загружает original в private quarantine через короткий presigned PUT. Backend
   преобразует внутренний MinIO URL в same-origin `/media-storage/...`; reverse proxy удаляет
   этот prefix, восстанавливает подписанный `Host: minio:9000` и передаёт запрос в private
   MinIO. Storage request не содержит session cookie, а bucket не получает public policy.
3. Backend подтверждает фактический MinIO size и одной PostgreSQL transaction фиксирует durable
   media job вместе с dispatch intent. Reconciler доставляет job UUID в Dramatiq независимо от
   browser request и восстанавливает сообщение после временного сбоя или очистки broker.

При student read media берётся только из последнего immutable published snapshot. Backend
повторно сверяет asset status и каждый variant по name, MIME, dimensions и SHA-256 с текущей
private storage metadata; только после этого создаётся короткий same-origin presigned GET.
Несовпавший или исчезнувший variant пропускается, а API response с signed URLs имеет
`Cache-Control: no-store`.
4. Worker проверяет size, MIME/magic bytes, декодирует с resource limits, создаёт variants
   и сохраняет hashes/metadata в PostgreSQL; image pipeline не увеличивает originals.
   Video worker выполняет bounded `ffprobe`, локальный H.264/AAC transcode и WebP poster,
   повторно проверяет rendition и сохраняет coarse-grained phase/progress после этапов.
5. Asset становится `ready` либо `rejected`; completion атомарно фиксирует progress `100`,
   partial objects удаляются retention job.

## Согласованность и отказоустойчивость

- PostgreSQL constraints и transaction recheck обеспечивают correctness; Redis lock снижает
  конкуренцию, но его потеря не нарушает инварианты.
- `job_dispatches` — transactional dispatch intent для import/image/video. Reconciler использует
  `FOR UPDATE SKIP LOCKED`, bounded batch, delivery lease и не более `max_attempts`. Crash между
  send и отметкой delivery может дать duplicate, но не потерю; actor idempotency делает его
  безопасным.
- Dramatiq actors idempotent по job UUID и повторно читают durable state.
- Retry разрешён только для transient failures с exponential backoff и max attempts.
  Validation, authorization, parser drift и quota failures не ретраятся автоматически.
- Claim выполняется под PostgreSQL row lock. Активный `running` heartbeat образует lease;
  повторная доставка пропускается, а просроченная lease может быть безопасно перехвачена.
- `queued → running → retrying → running` повторяется в пределах `max_attempts`; terminal
  result — только `succeeded` или `failed`. Dramatiq retry delay и `next_retry_at` фиксируются
  согласованно. Очистка Redis не переписывает durable status: reconciler повторно доставляет
  старый `queued`, due `retrying` или `running` с истёкшей heartbeat lease. Исчерпание delivery
  attempts переводит job в safe `failed`, после чего нужен явный audited retry.
- Administrator monitor читает PostgreSQL с фильтрами и polling. Ручной retry разрешён только
  для `failed` (повторный запрос к уже `queued` лишь повторяет доставку) и записывается в audit.
- Object upload и DB commit не атомарны: orphan/pending objects убирает audited retention job.
- Ошибки внешнего источника не меняют уже published component и не скрываются.

## Deployment boundaries

`parser-egress` is shared by the parser worker and backend repository acquisition boundary.
The backend uses it only for administrator-only bounded discovery and preview; durable imports
continue to run in the dedicated parser worker. Media processing remains without external egress.

Reverse proxy — единственная опубликованная точка входа. PostgreSQL, Redis, MinIO admin API,
backend и media worker остаются в internal container networks без внешнего egress. Parser worker
и backend repository boundary подключены к отдельной egress network для allowlisted HTTPS fetch.
Эта Docker network не является destination firewall: independent host/network egress rules,
internal TLS, backups, monitoring и restore drill обязательны перед production. Credentials
поступают через ignored production environment mechanism и не хранятся в Git. Production overlay
разделяет PostgreSQL migration owner и DML-only runtime role, включает password-authenticated
Redis и выдаёт приложению отдельную bucket-scoped MinIO policy вместо root credentials.
Одноразовые `database-permissions` и `minio-identity-init` завершаются до запуска backend/workers.
Отдельная read-only PostgreSQL backup role используется pinned `pg_dump`; restore допускается
только владельцем в изолированную базу `ackb_restore_*`, проверяет privacy-safe manifest и затем
применяет Alembic head. Автоматический drill проверяет clean install и upgrade с предыдущего head.
Exact trusted Host и same-origin middleware сохраняют внешний DNS hostname как browser boundary.

## Решения, отложенные до следующих этапов

Локальные opaque server-side sessions утверждены как MVP baseline. Возможная интеграция с
колледжным SSO не должна менять backend RBAC, отзыв сессий и audit invariants. Outbox
implementation и согласованный PostgreSQL+MinIO backup orchestrator остаются отложенными.
PostgreSQL identity/tooling и restore drill реализованы на этапе 17. Merge/review UI уже
реализован.

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
