# Контроли безопасности

Документ фиксирует реализованные меры защиты и эксплуатационные требования. Перечень активов,
границ доверия, угроз и остаточных рисков находится отдельно в
[модели угроз](THREAT_MODEL.md). Архитектурные потоки описаны в [ARCHITECTURE.md](ARCHITECTURE.md).

## Идентификация и доступ

- Backend является единственным источником истины для authentication, permissions и object
  visibility; frontend guards влияют только на интерфейс.
- Локальные пароли хешируются Argon2id. Неизвестный login проходит dummy verification и получает
  тот же ответ, что неверный пароль.
- Browser получает opaque server-side session и отдельный CSRF token. PostgreSQL хранит только
  SHA-256 hashes; production cookie имеет `HttpOnly`, `Secure` и `SameSite=Lax`.
- Каждый запрос заново проверяет active user, session expiry/revocation и действующие role grants.
  Отключение пользователя и изменение роли отзывают его сессии.
- Login throttling хранится в PostgreSQL по HMAC-псевдонимам account и client. Пароли, tokens и
  client address не попадают в audit.
- Default deny применяется и к маршруту, и к объекту. Чужой и отсутствующий UUID возвращают
  одинаковый `404`, если подтверждение существования объекта раскрыло бы данные.

### Матрица ролей

| Роль | Разрешённый scope |
|---|---|
| `student` | Только опубликованный каталог и общие справочные данные |
| `teacher` | Каталог и отдельное предложение исправления без прямого edit |
| `editor` | Собственные draft, media и imports; отправка на review |
| `administrator` | Review/publish, users/roles, sources, audit, diagnostics и duplicate decisions |

Только administrator управляет пользователями, source policy, публикацией и duplicate merge.
Временный editor всегда сохраняет безопасную базовую роль, имеет `expires_at`, а его grant history
не удаляется после истечения или отзыва.

## Browser и API

- State-changing cookie request требует session-bound double-submit CSRF cookie/header.
- API работает только same-origin; permissive CORS отсутствует, Origin и trusted Host проверяются
  до маршрутизации.
- CSP разрешает production assets только same-origin; также заданы `nosniff`, frame protection,
  Referrer Policy и Permissions Policy.
- React выводит пользовательские данные как text nodes. Raw HTML, remote script, iframe и
  исполняемый Markdown не поддерживаются.
- Любая ошибка использует bounded envelope `code`, русское `message`, `retryable`, `request_id`.
  Traceback, SQL, внутренние адреса и parser payload наружу не возвращаются.
- Published API читает immutable snapshot и не сериализует draft, teacher notes, storage keys или
  administrative metadata.

## Parser и внешние источники

Parser создаёт только draft независимо от confidence и не имеет publish/merge permission.

- Website sources используют exact allowlist и source policy до network access. Отключённый или
  запрещённый источник не запрашивается.
- Repository import принимает `source_key`, revision и bounded path, но не произвольный repository
  URL. Revision разрешается до полного commit SHA.
- HTTPS transport повторно проверяет каждый DNS answer и redirect, блокируя private, loopback,
  link-local и зарезервированные адреса; ограничены ports, redirects, response size и timeouts.
- Snapshot не запускает Git hooks, submodules, package scripts или documentation build.
- Markdown/MDX parser не исполняет YAML objects, JSX, imports, expressions и code blocks. KiCad
  parser использует bounded S-expression reader без shell/KiCad process.
- Source body и произвольный exception не логируются. Provenance, license snapshot, parser version
  и immutable revision сохраняются рядом с draft.
- Evidence-first pipeline работает в `disabled` или `shadow`, пока gates из
  [roadmap](imports/ROADMAP.md) не разрешат authoritative switch.

## Upload и медиа

- Upload session создаёт серверный object key и короткий presigned URL в private MinIO quarantine;
  client не выбирает bucket или storage path.
- Backend проверяет declared/actual size, extension, MIME и magic bytes. Image decoder ограничивает
  dimensions/frames и запрещает trailing/polyglot data; результат re-encode удаляет metadata.
- Video проверяется bounded `ffprobe`/FFmpeg без shell и с allowlist протоколов. Limits охватывают
  размер, длительность, dimensions, frames, CPU, memory, process count и timeout.
- Media worker не имеет внешнего egress и работает с read-only filesystem, bounded tmpfs,
  dropped capabilities и `no-new-privileges`.
- PostgreSQL хранит media metadata и state, MinIO — только binary media. Published snapshot
  содержит ordered asset/variant identity и SHA-256, но не bucket/object keys.
- Publication требует готовые assets и ровно одно primary image. Failed/abandoned objects удаляет
  audited retention job, причём destructive mode требует явный `--apply`.

## Данные, журнал и поиск

- PostgreSQL — durable source of truth. Redis служит Dramatiq broker, lock/rate-limit cache и не
  определяет итоговое состояние job.
- Любое изменение схемы выполняется Alembic; runtime `create_all` запрещён.
- Audit append-only для HTTP/UI: запись идёт внутри server mutation transaction, чтение требует
  `audit.view`, а mutation endpoint для журнала отсутствует.
- Allowlist audit fields запрещает password, token, cookie, presigned URL, raw upload/source и
  вложенный произвольный payload.
- Поиск строится только из immutable published snapshot. Draft, teacher notes, solutions и code
  examples не входят в индекс; SQL использует bind parameters.
- Backup manifest содержит counts и безопасные fingerprints, но не password hashes или content.
  Сам dump остаётся конфиденциальным и хранится зашифрованно вне VM.

## Инфраструктура

- Reverse proxy — единственная опубликованная точка. PostgreSQL, Redis, MinIO, backend и workers
  находятся во внутренних сетях; parser egress выделен отдельно.
- Production preflight запрещает placeholder credentials, wildcard Host, insecure cookies/MinIO,
  DEBUG/docs, Redis без пароля, bootstrap database role и root MinIO identity.
- Runtime PostgreSQL role имеет только DML, migration owner — DDL, backup role — read-only.
  MinIO application policy ограничена private buckets; root identity не передаётся приложению.
- Application containers запускаются non-root с read-only filesystem и минимальными Linux
  capabilities. Версии runtime и base images закреплены; dependency audit обязателен в CI.
- Internal TLS, host firewall, egress policy, secret rotation, monitoring и согласованный
  PostgreSQL + MinIO backup остаются обязанностью deployment.

## Доступность и восстановление

- Import/media job и `job_dispatch` создаются одной PostgreSQL transaction. Reconciler доставляет
  opaque UUID в Dramatiq и восстанавливает потерянные сообщения из durable state.
- Actors идемпотентны по job UUID; row lock, heartbeat lease, bounded retry/backoff и max attempts
  предотвращают бесконечную или параллельную обработку.
- Validation, authorization, quota и parser drift не повторяются автоматически. Ручной retry
  проходит RBAC, ownership, CSRF и audit заново.
- Per-user/global quotas и отдельные queues не дают video/import нагрузке вытеснить каталог.
- Restore разрешён только в изолированную базу `ackb_restore_*`; после проверки manifest схема
  доводится до Alembic head.

## Обязательные проверки

1. Прямые API-запросы подтверждают RBAC каждой роли, CSRF и одинаковый foreign/missing `404`.
2. SSRF fixtures покрывают DNS rebinding, redirects и non-public addresses.
3. Upload fixtures покрывают MIME mismatch, oversized/decompression bomb, polyglot и malformed
   media.
4. Parser fixtures подтверждают отсутствие исполнения MDX/code и сохранение provenance.
5. Published/search responses не раскрывают draft и teacher-only данные.
6. Dependency audits, migration tests, clean-stack и restore smokes входят в release CI.
7. Целевой стенд отдельно проверяет TLS, firewall, egress, backups и alerting.
