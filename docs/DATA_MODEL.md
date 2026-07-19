# Модель данных

Документ задаёт логическую PostgreSQL-модель. Он не является миграцией. Физическая схема
будет вводиться последовательными Alembic revisions; приложение не вызывает `create_all`.

## Соглашения

- Primary keys — UUID; timestamps — `timestamptz` в UTC.
- Mutable aggregate содержит integer `revision` для optimistic locking.
- Business enums задаются PostgreSQL enum либо `text` + `CHECK`, но меняются только Alembic.
- User text сохраняется как plain text/Markdown без raw HTML.
- Binary media нет в PostgreSQL: только MinIO bucket/object key и metadata.
- Foreign keys и unique constraints являются последней линией защиты, не заменяя validation.

## Identity и RBAC

### `users`

`id`, `login`, `display_name`, `password_hash`, `status(active|disabled)`, `created_at`,
`updated_at`, `last_login_at?`.

Unique: normalized `login`. В MVP используется локальная auth; пароль хранится только как
Argon2id hash. Переход к SSO потребует отдельной Alembic migration, а не перегрузки полей.

### `user_roles`

`user_id`, `role(student|teacher|administrator)`, `granted_by`, `granted_at`.

Primary key: `(user_id, role)`. Service identity и database credentials не моделируются
как человеческая роль.

### `auth_sessions`

`id`, `user_id`, `token_hash`, `csrf_hash`, `created_at`, `expires_at`, `last_seen_at`,
`revoked_at?`.

Unique: `token_hash`; `expires_at > created_at`. Raw session и CSRF tokens не сохраняются.
Запрос действителен только для active user, непросроченной и неотозванной сессии.

### `auth_throttles`

`key_hash`, `failure_count`, `window_started_at`, `blocked_until?`, `updated_at`.

Primary key — HMAC-SHA-256 pseudonym account/client key с отдельным secret pepper. Login и
client address в таблице не хранятся. Row/advisory locks сериализуют конкурентные попытки.

## Каталог

### `components`

`id`, `slug`, `status(draft|published|archived)`, `title`, `manufacturer?`, `model?`,
`summary`, `description`, `purpose?`, `usage_notes?`, `safety_notes?`, `difficulty`,
`teacher_notes?`, `primary_category_id`, `manual_original`, `created_by`, `updated_by`,
`published_at?`, `created_at`, `updated_at`, `revision`.

Unique: `slug`. Checks: title/summary lengths, `published_at IS NOT NULL` только для
published/archived published record, `revision > 0`.

Published history нельзя надёжно представить только mutable row. При реализации CRUD
добавляется `component_revisions` с immutable content snapshot, `revision`, actor и timestamp;
`components` указывает на current draft и current published revision.

### `component_aliases`

`id`, `component_id`, `alias`, `normalized_alias`, `position`.

Unique: `(component_id, normalized_alias)`; не более 20 обеспечивается application rule
под row lock.

### `categories`

`id`, `key`, `name`, `parent_id?`, `description?`, `is_active`, `position`.

Unique: `key`; parent не может ссылаться на себя. Используемая категория деактивируется
либо требует reassignment, но не удаляется каскадно.

### `tags` и `component_tags`

`tags`: `id`, `name`, `normalized_name`; unique normalized name.
`component_tags`: `(component_id, tag_id)`; максимум 20 — application rule.

### `units`, `property_definitions` и `component_properties`

`units`: `id`, stable `key`, `symbol`, `name`. `property_definitions`: `id`, stable `key`,
`label`, `value_type(text|number|boolean)`, `unit_id?`, `is_multivalue`.
`component_properties`: `id`, `component_id`, `definition_id`, `value_text`, `value_number?`,
`position`.

Numeric representation используется для будущей фильтрации, но `value_text` сохраняет
отображаемый смысл. В текущем редакторе один stable key встречается в карточке один раз;
несовместимое переопределение общего key отклоняется, а не молча заменяет definition.

### `component_pins`

`id`, `component_id`, `label`, `number?`, `mode?`, `voltage?`, `description?`, `position`.

### `component_interfaces`

`id`, `component_id`, `kind`, `details?`; unique `(component_id, kind, details)`.

### `component_compatibility`

`id`, `component_id`, `target_type(board|library|platform)`, `name`, `version_constraint?`,
`notes?`.

Таблица добавлена Alembic revision `20260716_07`; порядок задаётся `position`.

### `code_examples`

`id`, `component_id`, `title`, `language`, `practical_task`, `body`, `libraries_json`,
`explanation?`, `visibility(student|teacher)`, `position`, `created_by`, `updated_at`.

Body — text до 64 KiB; он никогда не исполняется backend/worker.

### `code_example_hints`

`id`, `example_id`, `body`, `position`; unique `(example_id, position)`. До 10 подсказок
по 2 000 символов раскрываются строго по `position`. Таблицы учебного блока добавлены
revision `20260716_11`.

## Источники и импорт

### `sources`

Основные поля: `id`, `key`, `display_name`,
`source_type(website|git_repository|official_library)`, `status(active|inactive|disabled)`,
`seed_url`, `allowed_host?`, `repository_url?`, `repository_owner?`, `repository_name?`,
`default_revision_policy(immutable_commit|release_tag)`, `adapter`, `adapter_version`,
`policy`, `content_policy`, `license_name?`, `license_spdx?`, `license_url?`,
`attribution_template?`, `permission_status(unknown|denied|license_granted)`, `disable_reason?`,
`allow_text_import(none|limited|full)`, отдельные allow flags для facts/media/code/attachments,
`is_enabled`, `created_by`, `updated_at`.

`seeed_wiki` и `kicad_symbols` активны и имеют immutable repository/license policy.
`alexgyver` disabled/denied с `owner_denied_usage`; `arduino_tex` и `portal_pk` inactive/unknown.
Исторические rows не удаляются. Partial unique index защищает `repository_url`.

### `component_sources`

Сохраняет прежние URL/hash поля и immutable repository snapshot:
`source_revision?`, `source_tag?`, `source_file_path?`, `source_entry_name?`, `original_url?`,
`imported_at?`, `imported_fields`, `provenance_json`, `modifications_notice?`,
`license_snapshot_name?`, `license_snapshot_spdx?`, `license_snapshot_url?`,
`attribution_snapshot?`, `parser_name?`, `parser_version?`.

Repository unique identity: `(source_id, source_revision, source_file_path, source_entry_name)`.
Старый `(source_id, source_item_id)` применяется только к website rows без revision. Полный
commit имеет 40 lowercase hex symbols. License snapshot не вычисляется заново при чтении.

### `import_jobs`

`id`, `source_id`, `submitted_url`, `canonical_url?`, `repository_url?`,
`requested_revision?`, `source_revision?`, `source_file_path?`, `source_entry_name?`,
`status(queued|running|retrying|succeeded|failed)`, `requested_by`, `idempotency_key`, `attempts`,
`max_attempts`, `parser_name?`, `parser_version?`, `parse_status?`, `warnings_json`,
`draft_component_id?`, `error_code?`, `created_at`,
`started_at?`, `next_retry_at?`, `finished_at?`, `updated_at`.

Unique: `(requested_by, idempotency_key)`. `succeeded` требует `draft_component_id`;
`failed` требует typed `error_code`. Job result никогда не указывает на автоматически
published component.

Revision `20260716_08` создаёт baseline URL tables. Revision `20260716_13` расширяет их для
repository/license snapshots и seed policy без удаления истории. `ParsedComponent` фиксирует
persistence contract: `status=draft`, `source_policy=metadata_only`, `source_host`,
`source_url`, `canonical_url`, `source_item_id`, `source_content_sha256`, `parser_name`,
`parser_version`, `parsed_at`,
bounded `title/summary/description`, aliases/model/category hint/tags. Поля published/merge и
binary body отсутствуют. Нормализованные `components.normalized_manufacturer` и
`components.normalized_model` заполняются application service; parser worker сохраняет только
draft и provenance. Любое DDL выполняется только Alembic.

`ParsedRepositoryComponent` всегда имеет `draft_status=draft`, full commit, registered
repository, typed parse status, normalized fields, provenance каждого поля, license snapshot,
attribution и modifications notice. Seeed idempotency включает source/repository/commit/file;
KiCad дополнительно включает entry name. Новая revision не обновляет существующую published
revision автоматически.

Каждый adapter имеет стабильные `parser_name` и semantic `parser_version`; fixture update,
который меняет извлечение полей, требует новой parser version. Drift diagnostic является
операционным результатом ошибки и не хранит remote HTML или binary payload.

## Медиа

### `media_assets`

Реализованный media baseline: `id`, `owner_user_id`, `component_id?`, `kind(image|video)`, `purpose`,
`alt_text`, `attribution?`, `status(pending|processing|ready|rejected)`, `bucket`, `object_key`,
`declared_mime`, `declared_size_bytes`, `detected_mime?`, `size_bytes?`, `sha256?`, `phash?`,
`width?`, `height?`, `duration_ms?`, `video_codec?`, `audio_codec?`, `frame_rate?`,
`failure_code?`, `upload_expires_at`, `created_at`, `updated_at`.

Unique: `(bucket, object_key)`. Checks отражают лимиты из REQUIREMENTS. `ready` требует
detected MIME, SHA-256 и dimensional metadata. Object key UUID-based; binary column запрещён.
`component_id` временно nullable и без FK до появления таблицы `components`; связывать с
published revision можно будет только `ready` asset отдельной следующей миграцией.

### `media_variants`

`id`, `asset_id`, `variant(320w|800w|1600w|video_720p|poster)`, `bucket`, `object_key`,
`mime`, `size_bytes`, `sha256`, `width`, `height`, `duration_ms?`, `video_codec?`,
`audio_codec?`, `frame_rate?`.

Unique `(asset_id, variant)` и `(bucket, object_key)`. Variant наследует authorization
родительского asset.

### `media_jobs`

`id`, `asset_id`, `status(queued|running|retrying|succeeded|failed)`, `attempts`,
`max_attempts`, `manual_retry_count`, `idempotency_key`, `queue_name`, `task_name`,
`error_code?`, `phase`, `progress_percent(0..100)`, `heartbeat_at?`, `next_retry_at?`,
`last_enqueued_at?`, `created_at`, `started_at?`, `finished_at?`, `updated_at`.

Unique `(asset_id)` и `(idempotency_key)`. PostgreSQL является durable источником статуса;
Redis хранит доставку, но не подменяет job state. `attempts <= max_attempts`, lease определяется
heartbeat, validation failure терминален, transient storage failure получает bounded backoff и
после исчерпания попыток становится видимым `media_storage_failed`.

## Дедупликация и audit

### `duplicate_candidates`

`id`, `left_component_id`, `right_component_id`, `kind(exact|fuzzy)`,
`status(open|merged|rejected|superseded)`, `score`, `algorithm_version`, `evidence_json`,
`created_at`, `resolved_at?`, `resolved_by?`.

Canonical pair хранится в упорядоченном виде, unique для открытой пары и версии алгоритма.
`score` ограничен `0..1`; evidence не содержит raw HTML или секретов.

Таблица добавлена revision `20260716_09`. `fuzzy-v1` сохраняет breakdown для title trigram,
tokens, manufacturer/model identity, spec fingerprint, нормализованных text hashes, media
SHA-256/pHash и отдельные penalties конфликтов. Предварительная выборка ограничена 50 строками;
candidate сохраняется при `score >= 0.35`, а open candidate с `score >= 0.70` блокирует
publication до отдельного административного решения этапа review.

### `merge_decisions`

`id`, `candidate_id`, `decision(merge|attach|create|reject)`, `survivor_component_id?`,
`field_resolution_json`, `reason`, `decided_by`, `decided_at`, `before_snapshot`,
`after_snapshot?`.

`decided_by` обязан иметь administrator permission на момент команды; это проверяет backend.
Для `merge/attach` survivor обязателен, для `create/reject` запрещён. Одна candidate имеет не
более одного решения; before/after snapshots и отдельный audit event сохраняют доказательства.
Merge decision immutable. Таблица добавлена revision `20260716_10`.

### `audit_events`

`id`, `occurred_at`, `actor_user_id?`, `actor_type(user|worker|system)`, `action`,
`object_type`, `object_id?`, `request_id?`, `job_id?`, `outcome`, `details_safe_json`,
`previous_event_hash?`, `event_hash?`.

Append-only права database role; application не имеет UPDATE/DELETE. Детали не содержат
паролей, tokens, presigned URLs, full session identifiers или remote response bodies.

## Поисковый документ опубликованной карточки

### `published_search_documents`

Одна строка на опубликованный component: `component_id` (PK/FK), `revision`, `category_id`,
`difficulty`, `title`, `aliases_text`, `manufacturer`, `model`, `summary`, `tags_text`,
`search_text`, weighted `search_vector`, `published_at`.

Документ является производной read model только от immutable published snapshot. Backend
перезаписывает его через PostgreSQL upsert при публикации и удаляет при archive; binary и
teacher-only данные отсутствуют. GIN `ix_published_search_vector` обслуживает FTS, GIN
`ix_published_search_trigram` с `gin_trgm_ops` — word-similarity fallback, B-tree индексы
покрывают category/difficulty. Revision `20260716_12` создаёт таблицу и backfill последних
published revisions существующих неархивированных карточек.

## Ключевые отношения

```text
users --< user_roles
users --< auth_sessions
auth_throttles
categories --< components --< component_revisions
components -- published_search_documents
components --< specifications / pins / interfaces / compatibility / code_examples
components >--< tags
sources --< component_sources >-- components
sources --< import_jobs >-- draft components
components --< media_assets --< media_variants
components >-- duplicate_candidates --< merge_decisions
users / workers --< audit_events
```

## Инварианты миграций

1. Каждая schema change имеет Alembic upgrade/downgrade либо документированную
   irreversible operation с backup/restore plan.
2. Deployment выполняет migration отдельным шагом до запуска несовместимого приложения.
3. destructive migration разделяется на expand/backfill/contract и не прячет потерю данных.
4. Tests поднимают схему через `alembic upgrade head`, а не ORM table creation.
