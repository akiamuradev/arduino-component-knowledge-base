# Безопасность

## Модель угроз и границы доверия

Недоверенными считаются browser input, upload, URL и содержимое внешних сайтов, media
metadata, Markdown/code examples, очередь сообщений и все данные, ранее записанные parser.
PostgreSQL, Redis и MinIO доступны только внутри deployment network, но компрометация одного
сервиса не должна автоматически давать administrative API permission.

Защищаемые активы: учётные записи и сессии, unpublished учебные материалы, скрытые решения,
аудит, карточки и их provenance, media objects, backup и инфраструктурные credentials.

## Authentication и authorization

- Backend является источником истины: route dependency проверяет authentication, application
  service — action permission, repository query — object visibility.
- Default deny. Student видит только published revision и student-visible examples.
- `/api/v1/catalog/*` требует active session, не сериализует `teacher_notes` и не возвращает
  карточку без published snapshot либо после archive; frontend route guard не заменяет эту проверку.
- технические поля student API восстанавливаются из published snapshot, а не из редактируемого
  draft head; текст значений выводится React text nodes без raw HTML execution.
- Teacher управляет draft и публикацией без merge-конфликта. Только administrator управляет
  ролями/source policy и подтверждает duplicate merge.
- MVP использует локальные Argon2id credentials и opaque server-side sessions. PostgreSQL
  хранит только SHA-256 hashes session/CSRF tokens; session cookie имеет `HttpOnly`, `Secure`
  в production и `SameSite=Lax`.
- Disabled user и role change централизованно отзывают его сессии. На каждом запросе backend
  повторно проверяет status, session expiry/revocation и текущие роли.
- State-changing cookie request требует double-submit CSRF cookie/header, причём hash token
  привязан к server-side session; tokens не хранятся в `localStorage`.
- Login ограничен persistent PostgreSQL counters одновременно по HMAC-псевдонимам account и
  client. Неизвестный login проходит Argon2id dummy verification и получает общий ответ.
- Login, import, upload, presign и administrative actions имеют rate limits и audit.
- Frontend route guard не считается security control; прямой API вызов получает тот же deny.
- Frontend API base обязан быть same-origin path. `fetch` отправляет opaque cookies только в
  `/api/v1`; CSRF cookie читается лишь для формирования header mutation-запроса.
- Session token и role snapshot не сохраняются в `localStorage`/`sessionStorage`. Query cache
  очищается после logout, а защищённый route всегда зависит от backend `/auth/me`.
- Editorial preview не использует `dangerouslySetInnerHTML`: до отдельного проверенного
  Markdown renderer содержимое отображается как text. Teacher notes остаются внутри
  защищённого workspace и не входят в student layout.
- Save/publish/archive передают optimistic revision. `409 revision_conflict` запрещает
  автоматический retry и blind overwrite; локальная форма сохраняется до решения пользователя.
  Операции выполняются под PostgreSQL row lock и создают immutable revision snapshot.
- Security route-matrix test проверяет, что `/admin` и duplicate review остаются
  administrator-only, workspace/media/import — teacher/administrator, а каждая authenticated
  mutation содержит CSRF dependency. Foreign media/import identifiers дают одинаковый `404`.

## Browser boundary: CSRF, CORS и CSP

- API является same-origin. Backend сравнивает каждый присутствующий `Origin` с внешними
  scheme/Host (включая forwarded host port) и fail-closed отклоняет `null`, userinfo, path,
  другой host/port/scheme и CORS
  preflight. `Access-Control-Allow-Origin` намеренно не выдаётся.
- Double-submit CSRF остаётся обязательным для authenticated mutations даже при SameSite cookie;
  login является единственной mutation без существующей session.
- FastAPI и reverse proxy задают одинаковые CSP, `nosniff`, deny framing,
  `Referrer-Policy: no-referrer`, COOP и restrictive Permissions-Policy. CSP разрешает scripts,
  styles и API connection только same-origin; images/media дополнительно допускают local blob.

## SSRF-защита parser

Исторический HTML fetcher технически распознаёт exact host `arduino-tex.ru`, `portal-pk.ru` или
`alexgyver.ru`, но database policy помечает их inactive/denied. API и worker требуют active
license-granted source до network access, поэтому новый или ранее queued job этих сайтов не
может выполнить HTTP request.

Для initial target и каждого redirect обязательны:

1. strict parse, IDNA normalization и canonicalization;
2. DNS resolve всех A/AAAA records;
3. запрет loopback, private, link-local, multicast, reserved, unspecified, CGNAT,
   IPv4-mapped IPv6 и metadata/service ranges;
4. connection pinning к проверенному IP с исходным Host/SNI и TLS verification;
5. повторная allowlist/DNS/IP проверка redirect, максимум 3 redirects;
6. запрет system proxy, cookies, credentials и forwarding Authorization;
7. connect/read/total timeout, response header limit и максимум 2 MiB HTML;
8. только `text/html`/ожидаемый MIME; archive, file download и JavaScript execution запрещены.

Allowlist не отменяет IP validation: DNS trusted host может быть скомпрометирован. Application
ограничивает назначения, но независимый egress firewall только к DNS и 443 должен быть настроен
на host/network layer. Default Compose сам это правило не обеспечивает.

Реализованный HTTPX fetcher формирует connection URL из проверенного IP, но сохраняет
исходный allowlisted host в Host header и SNI для TLS hostname verification. Все полученные
A/AAAA должны быть global; mixed public/private answer отклоняется целиком. Redirect не
следуется автоматически и проходит ту же проверку. `trust_env`, proxy и cookie forwarding
отключены; response читается потоково с лимитом decoded bytes. Fixture tests не обращаются к
сети и проверяют pinning, mixed DNS, redirect, MIME, cookie и body-limit случаи.

## Parser и content safety

Exact import координируется короткой Redis-блокировкой, но Redis не является источником
истины. Worker повторно проверяет canonical URL, source item ID и нормализованную пару
manufacturer/model в PostgreSQL transaction; UNIQUE indexes окончательно разрешают гонку.
Конфликт ограничения повторяется как bounded job, а не приводит к автоматическому merge.

- Каждый host имеет отдельный adapter и versioned fixtures. Неожиданная DOM-структура даёт
  `parser_drift`, а не частично успешную карточку.
- HTML преобразуется в ограниченный Markdown/plain text; raw HTML, script, style, iframe,
  event handlers, external embeds и active links не переносятся.
- Remote code sample сохраняется как text и никогда не компилируется/исполняется системой.
- Solution body отсутствует в DOM до явного раскрытия. Это UX-контроль, а не authorization:
  teacher-only example полностью отфильтровывается backend до student API response и snapshot.
- Syntax tokenizer не использует `innerHTML`, `eval`, dynamic import или server execution;
  даже HTML/JavaScript-подобный body остаётся экранированным React text.
- Field lengths, collection counts и Unicode normalization применяются до persistence.
- Parser создаёт только draft с provenance. Даже полностью валидный результат не получает
  `published`.
- Исторические website adapters остаются fixture-readable для audit/migration compatibility,
  но не доступны active import path и не сохраняют новые данные.
- Drift diagnostic содержит typed code и bounded adapter identity/field. Remote content,
  traceback и URL query не возвращаются оператору и не должны попадать в structured logs.
- Source policy `metadata_only` запрещает сохранение полного текста и binary media. Изменить
  policy может только administrator после документирования прав.

## Repository source safety

Local Compose attaches both the parser worker and backend to `parser-egress`. Backend egress is
limited in application code to administrator-only bounded repository discovery and preview using
the same allowlist, public-address validation, connection pinning, byte limits and timeouts as the
worker. Durable imports still execute only in the parser worker; media workers have no egress.

- Пользователь не передаёт произвольный Git URL. Допустимы только зарегистрированные exact
  repositories Seeed Studio Wiki и Official KiCad Symbols.
- Adapter принимает только полный commit SHA; branch/tag должен быть заранее разрешён backend.
  Revision входит в job, idempotency identity, provenance и immutable license snapshot.
- `RepositorySnapshot` принимает только relative POSIX paths, запрещает traversal/backslash,
  ограничивает file count и individual file size. Dry-run запрещает symlink root/file.
- Git hooks, submodules, package scripts, documentation build, KiCad CLI и remote code никогда
  не запускаются. На этапе 1 adapter работает с уже полученными bytes; безопасное bounded archive
  acquisition проверяется отдельно на Linux VM.
- Seeed MDX читается как UTF-8 data. Imports/exports, JSX expressions/tags, fenced code, images
  и attachments исключаются до field mapping.
- KiCad S-expression reader имеет byte/token/depth limits, не использует shell и обрабатывает
  неизвестный electrical type как warning конкретного symbol.
- Configured KiCad library prefixes приходят только из backend setting и имеют собственные
  count/length/path limits. Job input не может расширить allowlist.
- Publication импортированной карточки требует active/license-granted source, full revision,
  original/repository URL, SPDX/license URL, attribution и modifications notice. Проверка
  выполняется backend; frontend validation не является security boundary.

## Upload и media processing

- Buckets private; object key server-generated. Presigned PUT/GET короткоживущие, scoped к
  одному object/method и не логируются.
- До upload backend резервирует quota. После upload worker проверяет реальный размер,
  magic bytes и MIME независимо от filename/Content-Type.
- Pillow запускается с decompression-bomb limits, полной decode verification, ограничением
  20 MP/10 000 px; EXIF и прочая metadata удаляются при re-encode.
- SVG, animated images, archives и polyglots запрещены в MVP.
- `ffprobe`/FFmpeg запускаются non-root без shell, network и writable host filesystem, с
  CPU/memory/time/process limits. Input: до 256 MiB, 10 минут, 1080p/30 fps.
- Application adapter передаёт только фиксированный набор аргументов, закрывает stdin,
  ограничивает protocol whitelist до `file,pipe`, stdout/stderr, timeout и threads. Non-root,
  network/memory/process isolation
  обеспечиваются обязательным deployment container profile, а не доверием входному файлу.
- Rendition повторно проходит `ffprobe`: только MP4/H.264, optional AAC, до 1280×720/30 fps;
  poster обязан быть однокадровым metadata-free WebP до 1280×720.
- Студенту выдаётся только processed `ready` variant. Pending/rejected/original/quarantine
  недоступны через media API.
- SHA-256 обеспечивает exact dedup/integrity, perceptual hash — только fuzzy evidence.
- Quarantine и variants — разные private-by-default buckets. Provisioning не назначает policy
  и fail-closed отклоняет уже настроенную bucket policy; публичность не исправляется молча.
- Presigned upload TTL ограничен 15 минутами, URL не сохраняется в PostgreSQL/audit и ответы
  reservation/status помечены `Cache-Control: no-store`.

## Duplicate merge

- Exact/fuzzy detector создаёт candidate, но не изменяет компоненты.
- `fuzzy-v1` сохраняет только числовой breakdown и conflict counts: raw source text, media
  hashes и parser body в evidence не включаются. Algorithm version обязателен.
- Merge endpoint требует fresh administrator authorization и optimistic revision values.
- Backend блокирует обе записи и повторяет invariant checks в PostgreSQL transaction.
- Administrator выбирает survivor и каждое конфликтующее поле. Before/after snapshots,
  evidence, reason и actor записываются в immutable audit.
- Redis lock — оптимизация; uniqueness/transaction checks PostgreSQL остаются обязательными.
- Решения `merge/attach/create/reject` принимаются только admin API с CSRF; уникальность
  `candidate_id` не допускает повторного решения, а optimistic revisions останавливают stale UI.

## Secrets и инфраструктура

- Реальные secrets не находятся в Git, image layers, frontend bundle, fixtures, logs или
  documentation. `.env.example` содержит только placeholders.
- Local Compose читает PostgreSQL/MinIO credentials и auth pepper только из ignored `.env`;
  data services не публикуют host ports. Placeholder values непригодны для production.
- Default Compose пока переиспользует PostgreSQL bootstrap owner и MinIO root в runtime services.
  Отдельные least-privilege identities для migration, backend/worker, media и backup обязательны
  перед production; этот открытый finding отслеживается в `XRAY_AUDIT_0.21.0.md`.
- PostgreSQL, Redis и MinIO не публикуют host ports; MinIO console доступна только admin network.
- Reverse proxy завершает internal TLS, задаёт body/time limits и security headers.
- Production preflight fail-closed проверяет static IP, exact internal DNS, certificate SAN,
  цепочку CA, срок действия и mode private keys, но не изменяет сеть или firewall удалённой VM.
- HTTPS smoke не имеет insecure mode: edge hostname и CA обязательны; MinIO использует TLS и
  тот же read-only CA bundle, дополненный public roots для разрешённых внешних parser sources.
- Application images запускаются non-root; media worker и retention дополнительно имеют read-only
  filesystem/capability hardening. Остальные services ещё требуют такого же профиля. Python/npm
  версии и container bases зафиксированы; dependency audit входит в CI, container scan — нет.
- Alembic является единственным application DDL path, но runtime account в default Compose пока
  остаётся owner. Запрет CREATE/ALTER/DROP должен быть подтверждён отдельными production grants.
- Compose networks `edge` и `data` имеют `internal: true`; только reverse proxy дополнительно
  подключён к host-facing `ingress`, и наружу опубликован только reverse
  proxy. Media worker обслуживает только `images/videos` без external egress. Отдельный
  parser worker обслуживает только `imports`, и только он подключён к `parser-egress`.

## Logging, audit и privacy

Structured logs содержат request/job ID, typed error code и bounded labels. Запрещено
логировать passwords, tokens, cookies, presigned URLs, full remote response, raw upload,
teacher notes или URL query values. Ошибка не скрывается: клиент получает безопасный code,
оператор — correlation ID, audit — outcome.

Audit обязателен для login failures, role/source policy changes, import, upload rejection,
publication, archive, duplicate decision, merge и administrative export. Audit append-only,
имеет retention/backup и контролируемый доступ administrator.

Raw password, session/CSRF token, login throttle key и client address не попадают в audit.
Bootstrap первого administrator интерактивен, не принимает пароль через CLI и блокируется,
как только существует активный administrator.

## Availability и abuse controls

- Per-user и global quotas для concurrent imports/uploads; Dramatiq queues разделены для
  parser, images и video, чтобы тяжёлое video не блокировало каталог.
- Bounded exponential backoff только для transient errors; dead-letter/failed jobs видимы admin.
- PostgreSQL остаётся durable job truth, поэтому очистка Redis не превращает failed job в
  success и не отменяет audit.
- Общий monitor и ручной retry доступны только administrator через повторную backend RBAC
  проверку; mutation требует CSRF и audit. UI guard не заменяет эти проверки.
- Stable idempotency key, row lock и heartbeat lease ограничивают duplicate delivery. Monitor
  отдаёт typed error codes и coarse progress, но не raw exception, object URL или credentials.
- MinIO capacity, PostgreSQL storage, queue depth, failures и certificate expiry мониторятся.
- Backup охватывает PostgreSQL и versioned MinIO consistently; restore drill обязателен.

## Безопасность поиска

- Поисковый документ строится только сервером из published snapshot и не принимает готовый
  `tsvector` от клиента.
- Allowlist полей исключает draft descriptions, teacher notes, solutions, code examples,
  remote HTML и media keys; совпадение не может подтвердить существование скрытого текста.
- Query и фильтры передаются bind parameters. CLI диагностики принимает 1–100 символов,
  использует постоянный SQL и read-only transaction; пользовательский текст не становится SQL.
- Backend остаётся источником истины: публичная выдача дополнительно проверяет component
  `archived_at IS NULL` и активность category, даже если производный документ устарел.

## Security acceptance cases

1. Student получает `403` на draft, parser, upload, publish, audit и merge endpoints.
2. Teacher получает `403` на duplicate merge, role change и source policy change.
3. Parser result остаётся draft при любом confidence.
4. Redirect на private/loopback/link-local IP блокируется до connection.
5. Поддельные MIME, oversized/decompression-bomb image и over-duration video rejected.
6. Failed media/parser job виден как failed/rejected с typed code, не как successful.
7. Presigned URL не открывает другой object и истекает.
8. Merge без administrator permission или с устаревшей revision не изменяет данные.
9. Поиск, cache и media endpoint не раскрывают draft/teacher-only поля.
10. Schema tests используют Alembic head; runtime `create_all` отсутствует.
11. Teacher получает `403` на user/role administration; CSRF mismatch блокирует mutation.
12. Снятие роли или disable последнего active administrator отклоняется без изменения данных.
13. Teacher получает `403` на общий job monitor/retry; повторная delivery не запускает
    завершённую задачу, а transient retry остаётся `retrying`, не `failed` и не `succeeded`.
14. Все authenticated mutations кроме login имеют CSRF dependency; cross-origin request не
    получает CORS permission, а response содержит утверждённые CSP/security headers.
15. Foreign media/import ID не раскрывает существование объекта; media worker не подключён к
    parser egress, а data services находятся только в internal network.

## Остаточные риски этапа 0

- Права на импорт трёх сайтов ещё не подтверждены; до этого действует `metadata_only`.
- Реализация безопасного HTTP transport сложна и потребует отдельного adversarial review.
- SSO остаётся возможным следующим provider, но локальная opaque session model утверждена для
  MVP; retention sessions/audit и storage budget ожидают решения колледжа.
- Application формирует append-only audit API и использует proxy-aware client identity, но
  production database grants и внешний edge rate limit ещё требуют deployment hardening.
- Документы задают controls, но доказательства появятся только вместе с кодом, integration
  tests, deployment configuration, penetration testing и restore drill.
