# Архитектура

## Основные решения

- Backend определяет authorization, validation и state transitions; frontend не принимает
  решений о доступе.
- PostgreSQL — durable source of truth для каталога, identity, jobs, media metadata и audit.
- MinIO хранит private binary media, Redis обслуживает Dramatiq, locks и rate limits.
- Схема меняется только Alembic migrations; runtime `create_all` запрещён.
- Parser создаёт только draft. Publication и duplicate merge выполняет administrator отдельным
  подтверждённым действием.
- Published catalog читается из immutable revision snapshots, а не из редактируемого head.

## Контейнеры

```text
Browser
  -> reverse-proxy
       -> frontend (React + TypeScript + Vite)
       -> backend (FastAPI)
            -> PostgreSQL
            -> Redis / Dramatiq
            -> MinIO
       -> media worker (images/videos, без внешнего egress)
       -> parser worker (imports, выделенный parser-egress)
       -> job reconciler (durable dispatch)
```

Reverse proxy — единственный опубликованный сервис. Frontend использует только same-origin
`/api/v1`; backend выдаёт media URL после object-level проверки. PostgreSQL, Redis и MinIO не
публикуют host ports. Одноразовые migration и provisioning jobs завершаются до старта приложения.

## Модули

| Область | Ответственность |
|---|---|
| frontend `api/auth/routing` | Typed contracts, текущий principal, UX guards и query cache |
| frontend `pages/workspace` | Каталог, редактор, imports, review и administration screens |
| `identity` | Users, Argon2id credentials, sessions, roles и permissions |
| `catalog` | Components, categories, properties, lifecycle и published snapshots |
| `imports` | Source policy, acquisition, parsers, evidence-first pipeline и review |
| `media` | Upload sessions, validation, variants, delivery и retention |
| `deduplication` | Exact/fuzzy candidates и administrator decisions |
| `audit` | Append-only security и business events |
| infrastructure | PostgreSQL repositories, MinIO gateway, Dramatiq actors и HTTP transport |

FastAPI routes вызывают application services и не содержат SQL или S3 logic. Domain policies не
зависят от framework или storage adapters. Frontend permissions из `/auth/me` управляют только
видимостью элементов; каждый API action проверяется backend повторно.

## Ключевые потоки

### Вход и RBAC

1. Backend нормализует login, проверяет PostgreSQL throttle и Argon2id password hash.
2. Browser получает opaque `HttpOnly` session cookie и отдельный CSRF cookie; в базе хранятся
   только hashes и сроки действия.
3. Каждый запрос разрешает active user, session и непросроченные grants, затем проверяет
   permission и object visibility.
4. Изменение роли или disable отзывает sessions и создаёт audit event. Временный editor после
   `expires_at` возвращается к базовой роли без удаления авторства и истории.

### Каталог и редакционный цикл

1. Student API выбирает последний `published` snapshot активной неархивированной карточки.
2. Editor создаёт или изменяет `draft`; сохранение допускает неполные данные, но submit/publish
   валидируют обязательные поля, media и duplicate candidates.
3. Lifecycle: `draft → in_review → approved → published`; доступны запрос изменений, скрытие,
   обратимый archive и restore.
4. Каждая mutation использует expected revision и создаёт immutable component revision и audit.
5. Редактирование published head не меняет видимый snapshot до следующей публикации.

Teacher отправляет bounded correction proposal отдельно от карточки. Editor-владелец или
administrator отмечает его `applied`/`dismissed`; само предложение не меняет published content.

### Импорт

1. API проверяет role, CSRF, idempotency, source policy и bounded input.
2. `import_job` и `job_dispatch` создаются одной PostgreSQL transaction.
3. Reconciler публикует opaque job UUID; parser worker повторно проверяет durable state.
4. Acquisition разрешает repository revision до full SHA, проверяет DNS/redirect/size/time limits
   и получает только allowlisted paths.
5. Parser извлекает facts/provenance/license без исполнения source code и формирует только draft.
6. Persistence сохраняет result до terminal `succeeded`; typed failure доступен владельцу или
   administrator без traceback и source payload.

Исторические website adapters оставлены только для fixture compatibility и отключены source
policy. Активные Seeed Wiki и KiCad adapters работают с registered repository identity. KiCad
symbols используются как enrichment; module pins и symbol pins не смешиваются. Подробности и
условия переключения находятся в [import roadmap](imports/ROADMAP.md).

### Дубликаты и публикация

Detector создаёт candidate и versioned score evidence, не меняя карточки. Только administrator
может принять `merge`, `attach`, `create` или `reject`. Merge transaction блокирует candidate и
обе карточки, проверяет revisions, переносит выбранные связи, архивирует loser и сохраняет
immutable decision. Worker и parser не имеют этого transition.

### Медиа

1. Backend создаёт upload session и generated object key, затем отдаёт короткий presigned PUT в
   private MinIO quarantine. Изображения можно загрузить до первого сохранения draft.
2. Подтверждение upload проверяет storage size и одной transaction создаёт media job и dispatch.
3. Worker без внешнего egress проверяет MIME/magic/container limits, re-encode/transcode,
   формирует variants и записывает SHA-256 metadata.
4. Component row lock сериализует attach/order/primary/detach. Publication требует готовую
   коллекцию и ровно одно primary image.
5. Student получает только variants из immutable published snapshot; bucket, object key и original
   не сериализуются.

### Поиск

`published_search_documents` обновляется в той же transaction, что publication. Индекс содержит
только title, aliases, manufacturer, model, summary и tags. PostgreSQL использует weighted
`tsvector`, параметризованный `plainto_tsquery` и `pg_trgm` fallback; draft, teacher notes,
solutions и code examples не индексируются.

## Согласованность и восстановление

- PostgreSQL constraints, row locks и transaction recheck определяют correctness. Redis lock —
  только оптимизация.
- `job_dispatches` сохраняют intent до отправки в broker. `FOR UPDATE SKIP LOCKED`, delivery lease
  и max attempts позволяют восстановиться после сбоя Redis/worker без потери задачи.
- Actors идемпотентны по job UUID. Heartbeat lease разрешает безопасно перехватить зависший job;
  validation и authorization failures автоматически не повторяются.
- Object upload и database commit не атомарны, поэтому stale quarantine очищает retention job.
- Backup должен согласованно охватывать PostgreSQL и versioned MinIO; restore выполняется в
  изолированную базу и затем доводится до Alembic head.

## Deployment boundary

Локальный `compose.yaml` предназначен для localhost. Production overlay включает static bind,
internal TLS, secure cookies, отдельные PostgreSQL migration/runtime/backup roles,
password-authenticated Redis и bucket-scoped MinIO identity. Сети `edge` и `data` internal;
`parser-egress` отделён от media worker.

Container network не заменяет host firewall. External egress policy, DNS, CA, secret rotation,
capacity, monitoring и off-host backups настраиваются по [DEPLOYMENT.md](DEPLOYMENT.md) и
[OPERATIONS.md](OPERATIONS.md). Реализованные security controls перечислены в
[SECURITY.md](SECURITY.md).

## Отложенные решения

- Интеграция с SSO может заменить login provider, но не backend RBAC, session revocation и audit.
- Authoritative evidence-first import включается только после calibration и real-source shadow
  gates.
- Удаление legacy parser/schema выполняется после окна отката отдельными reversible migrations.
