# Требования

Статус: утверждаемая baseline-версия этапа 0 от 15 июля 2026 года.

## Назначение и границы

Система предоставляет студентам и преподавателям каталог Arduino-совместимых компонентов,
временным редакторам — наполнение базы, а администраторам — управляемый процесс проверки
и публикации карточек.
Основной режим эксплуатации — корпоративная сеть колледжа.

В MVP не входят публичная регистрация, публичный SaaS, YouTube, автоматическая публикация,
автоматическое объединение дубликатов и произвольный web crawler.

## Источники импорта

Активные источники являются только заранее зарегистрированными immutable Git repositories:

| Код | Repository | Тип | Лицензия | Политика |
|---|---|---|---|---|
| `seeed_wiki` | <https://github.com/Seeed-Studio/wiki-documents> | `git_repository` | `GPL-3.0-only` | факты и ограниченная адаптация текста |
| `kicad_symbols` | <https://gitlab.com/kicad/libraries/kicad-symbols> | `official_library` | `CC-BY-SA-4.0` | структурированные свойства и выводы |

Исторические website sources не удаляются. `alexgyver` имеет `status=disabled`,
`permission_status=denied`, `disable_reason=owner_denied_usage`. `arduino_tex` и `portal_pk`
имеют `status=inactive`, `permission_status=unknown`. Для них запрещены новые jobs и
публикация старых draft до появления разрешённого license snapshot.

REQ-SRC-001. Каждый источник реализуется отдельным versioned adapter. Произвольный URL или
Git repository от пользователя запрещён и не выбирает parser по содержимому.

REQ-SRC-002. Repository import принимает только зарегистрированный repository и полный
40-символьный commit SHA. Branch/tag разрешается backend в commit до создания durable job;
resolved SHA сохраняется в job, provenance и source snapshot.

REQ-SRC-003. `seeed-wiki-git-v1` читает Markdown/MDX как данные: frontmatter, headings,
таблицы и ссылки. MDX/JSX, imports, code blocks, images и attachments не выполняются и не
импортируются. Неизвестный необязательный раздел даёт warning, а не сбой всего документа.

REQ-SRC-004. `kicad-symbols-v1` разбирает `.kicad_sym` собственным bounded S-expression
reader без shell/external commands. Backend allowlist ограничивает библиотеки; пользователь
не может расширить allowlist параметром job.

REQ-SRC-005. Parser result имеет status `parsed`, `parsed_with_warnings`,
`unsupported_document`, `source_drift`, `invalid_metadata`, `license_missing` или `failed`.
Каждое сохранённое поле имеет repository, commit, file, section/property, confidence и
transformation.

REQ-SRC-006. Успешный parser job всегда создаёт только `draft`; parser не может установить
`published`, изменить published snapshot или объединить компоненты.

REQ-SRC-007. Идентичность Seeed включает source/repository/commit/file. Идентичность KiCad
дополнительно включает symbol name. Повтор той же revision переиспользует draft; новая revision
создаёт отдельный review candidate и не меняет опубликованную revision.

REQ-SRC-008. `component_sources` сохраняет immutable license snapshot, attribution,
modifications notice, repository/file/entry, parser version, imported fields и field provenance.
Изменение настроек `sources` не меняет уже опубликованный snapshot.

REQ-SRC-009. Imported draft нельзя опубликовать без display name, original/repository URL,
immutable revision, SPDX, license URL, attribution и modifications notice. Backend возвращает
typed error code. Manual original остаётся отдельным явно отмеченным типом материала.

REQ-SRC-010. Лицензия приложения не заменяет лицензию импортированных данных. Seeed media/code
и KiCad media/code/attachments не импортируются текущей политикой.

REQ-SRC-011. Одна повреждённая запись или необязательное поле не останавливает bounded batch;
warning и failure содержат безопасный code без raw document и traceback.

## Роли и авторизация

Роли являются backend enum и назначаются администратором. Frontend скрывает недоступные
действия только для удобства; окончательное решение всегда принимает backend.

| Действие | `student` | `teacher` | `editor` | `administrator` |
|---|:---:|:---:|:---:|:---:|
| Читать опубликованный каталог и разрешённые медиа | Да | Да | Да | Да |
| Читать draft и историю своего импорта | Нет | Нет | Да | Да |
| Создавать и редактировать draft вручную | Нет | Нет | Да | Да |
| Запускать parser для allowlisted источника | Нет | Нет | Да | Да |
| Загружать медиа в quarantine | Нет | Нет | Да | Да |
| Отправлять draft на проверку | Нет | Нет | Да | Да |
| Архивировать карточку без физического удаления | Нет | Нет | Да | Да |
| Проверять и публиковать карточки | Нет | Нет | Нет | Да |
| Подтверждать или отклонять duplicate merge | Нет | Нет | Нет | Да |
| Управлять пользователями, ролями, источниками и категориями | Нет | Нет | Нет | Да |
| Читать security audit и диагностику | Нет | Нет | Нет | Да |

Permissions задаются единым backend enum: `components.view`, `components.create`,
`components.edit`, `components.archive`, `components.delete`,
`components.submit_for_review`, `components.review`, `components.publish`,
`imports.view`, `imports.create`, `imports.retry`, `imports.cancel`, `users.view`,
`users.manage`, `roles.assign`, `audit.view`, `system.settings`,
`system.diagnostics`. Роль формирует только серверный набор permissions.

REQ-AUTH-001. Неаутентифицированный запрос не получает данные каталога; deployment может
использовать колледжный SSO либо локальные учётные записи, но публичная регистрация запрещена.

REQ-AUTH-002. Проверка разрешения выполняется backend для каждого API action и каждого
объекта. Отсутствующее разрешение даёт `403`, отсутствующая аутентификация — `401`.

REQ-AUTH-003. Worker использует отдельную service identity с минимальными правами и не
считается человеческой RBAC-ролью.

REQ-AUTH-004. MVP использует локальные Argon2id credentials и opaque server-side sessions.
Raw session/CSRF tokens не хранятся в PostgreSQL; state-changing запрос требует CSRF token,
привязанный к сессии. Public registration отсутствует.

REQ-AUTH-005. Login failures имеют persistent account/client throttling и единый ответ для
неизвестного login, неверного пароля и disabled user. Login/logout и управление identity
создают audit events без credentials, raw tokens и client address.

REQ-AUTH-006. Только administrator создаёт пользователей, меняет роли и отключает аккаунты.
Role change и disable отзывают активные сессии. Система не допускает удаления роли или
отключения последнего active administrator.

REQ-AUTH-007. Роль `editor` всегда имеет обязательный будущий `expires_at`. Просроченный
или явно отозванный grant немедленно перестаёт давать permissions, но остаётся в
`user_roles` вместе с `granted_by`, `granted_at` и `revoked_at` для истории.

REQ-AUTH-008. Русский экран `/admin/users` доступен только administrator. Создание временного
редактора всегда добавляет безопасную базовую роль `student`; отдельные grant/renew/revoke
запросы принимают user ID и срок, но не client-controlled role. Через этот workflow нельзя
назначить `administrator`. Создание, назначение, досрочный отзыв и disable журналируются.

REQ-AUTH-009. Русский экран `/admin/audit` и `GET /api/v1/admin/audit-events` доступны только
с серверным разрешением `audit.view`. Журнал является read-only: HTTP API не содержит операций
создания, изменения или удаления событий. Запись фиксирует UTC-время, пользователя или тип
системного субъекта, действие, объект и исход. Внешний response не включает request ID и
внутренние details. Фильтры по точному пользователю, действию и полуинтервалу дат выполняются
на backend; выдача ограничена и отсортирована от новых событий к старым.

Журнал покрывает вход, выход и ограниченные rate-limit политикой неудачные входы; создание и
блокировку пользователя; назначение, отзыв и изменение срока роли; создание, изменение,
переход состояния, публикацию и архивирование карточки; физическую retention-очистку; загрузку
компонента и файлов; повторную обработку; изменение категорий как системных настроек. Пароли,
cookies, raw tokens, throttle keys, client address, presigned URL и содержимое документов не
сохраняются.

## Карточка компонента

### Идентификация и жизненный цикл

- `id`: UUID, immutable;
- `slug`: уникальный стабильный URL key;
- `status`: `draft`, `in_review`, `changes_requested`, `approved`, `published`, `hidden`
  или `archived`;
- `archived_from_status`: предыдущий статус только для `archived`, нужен для обратимого restore;
- `title`: обязательное отображаемое имя, 2–160 символов;
- `aliases`: до 20 альтернативных имён, каждое до 100 символов;
- `manufacturer`: до 120 символов, nullable;
- `model`: до 120 символов, nullable;
- `primary_category_id`: обязательная категория;
- `tags`: до 20 тегов;
- `created_by`, `updated_by`, `created_at`, `updated_at`, `published_at`;
- `revision`: optimistic-lock integer.

### Учебное содержимое

- `summary`: обязательное краткое описание, 20–500 символов;
- `description`: Markdown, до 30 000 символов; raw HTML запрещён;
- `purpose`: назначение, до 2 000 символов;
- `usage_notes`: рекомендации, до 5 000 символов;
- `safety_notes`: предупреждения, до 5 000 символов;
- `difficulty`: `beginner`, `intermediate` или `advanced`;
- `teacher_notes`: до 10 000 символов, недоступны `student`;
- `code_examples`: до 10 примеров, каждый до 64 KiB, с language, title, body,
  visibility и объяснением; выполняться на сервере они не могут.

REQ-CARD-004. Каждый учебный пример содержит practical task, до 10 ordered hints,
скрытое до явного действия решение, до 20 названий библиотек и explanation. Student API
возвращает только `visibility=student` из опубликованного snapshot. Подсветка синтаксиса
создаёт только React text nodes и не компилирует, не интерпретирует и не запускает body.

### Технические данные

- до 50 структурированных specifications: key, label, value, optional numeric value, unit и
  display order;
- pins: label, number, mode, voltage и description;
- interfaces: например GPIO, ADC, PWM, UART, I2C, SPI, CAN;
- supply/logic voltage как specifications, без потери исходного текста;
- до 30 compatibility records: плата, библиотека или платформа, версия и примечание;
- wiring notes и ссылки на datasheet/source;
- media assets с kind, purpose, alt text, attribution и display order.

REQ-CARD-001. Публикация требует title, category, summary, description, хотя бы одного
source record или признака `manual_original`, а также отсутствия unresolved duplicate
candidate уровня `high`.

REQ-CARD-002. Публичная карточка отдаёт только опубликованную revision. Draft и скрытые
примеры не должны утекать через API, search index, media URL или cache.

REQ-CARD-003. Удаление опубликованной карточки логическое (`archived`); физическое удаление
допустимо только отдельной retention-процедурой с audit event.

REQ-CARD-005. Lifecycle имеет только серверные переходы:
`draft|changes_requested -> in_review`, `in_review -> changes_requested|approved`,
`approved -> changes_requested|published`, `published -> hidden`, `hidden -> published`,
любой неархивный статус может перейти в `archived`, а restore возвращает сохранённый
предыдущий статус. Editor создаёт и редактирует `draft`/`changes_requested`, может отправить
их на проверку и архивировать, но не может approve, publish, hide/show или физически удалить.
Administrator выполняет review и публикацию. Каждый переход требует CSRF, permission,
ожидаемую revision, допустимый исходный статус и audit event.

REQ-CARD-006. Редактирование опубликованной карточки создаёт новый рабочий `draft`, но не
удаляет последний immutable published snapshot из student catalog. Он заменяется только после
нового review и publish. `hidden` и `archived` исключаются из публичного API, search и media.

REQ-CARD-007. Каждая immutable revision хранит автора, время, предыдущее и новое состояние,
серверный тип действия и короткое безопасное описание изменения. Эти же метаданные входят в
audit event мутации. Editor читает историю только карточек, созданных им; administrator читает
историю всех карточек. Student/teacher и публичный API историю не получают. History response не
содержит snapshot payload, teacher notes, request identifiers или другие технические поля.
Disable пользователя не меняет историю, а физическое удаление account отсутствует и
дополнительно блокируется ссылочной целостностью revisions.

## Категории

Baseline taxonomy состоит из десяти верхнеуровневых категорий:

1. `boards` — микроконтроллерные платы и совместимые контроллеры;
2. `sensors` — датчики физических величин;
3. `actuators` — двигатели, реле, сервоприводы и исполнительные устройства;
4. `displays` — дисплеи, индикаторы и светодиодные матрицы;
5. `communication` — проводные и беспроводные интерфейсные модули;
6. `power` — питание, зарядка, преобразование и защита;
7. `input` — кнопки, клавиатуры, энкодеры, джойстики и другие органы ввода;
8. `prototyping` — breadboard, shield, проводники и соединители;
9. `passive` — резисторы, конденсаторы, диоды и дискретные элементы;
10. `other` — временная категория для модерации неизвестных типов.

REQ-CAT-001. Карточка имеет ровно одну primary category и произвольные tags. Подкатегории
могут добавляться администратором; код не должен зашивать taxonomy в frontend.

REQ-CAT-002. Parser только предлагает category с confidence и evidence. Teacher или
administrator подтверждает её перед публикацией.

REQ-CAT-003. Категорию, используемую карточками, нельзя удалить: сначала выполняется
явное reassignment. Изменение taxonomy — изменение данных, не DDL.

## Лимиты медиа

Все binary payload находятся в private MinIO buckets. PostgreSQL содержит только metadata,
object key, hashes, status и связь с карточкой. Object key генерируется сервером и не
содержит пользовательское имя файла.

| Тип | На карточку | Один original | Дополнительные ограничения |
|---|---:|---:|---|
| Изображение | 12 | 8 MiB | JPEG, PNG, WebP; до 20 MP; сторона до 10 000 px |
| Видео | 2 | 256 MiB | MP4, MOV, WebM; до 10 минут; до 1920×1080 и 30 fps |

Совокупный размер originals одной карточки — не более 600 MiB. Generated variants и
posters не учитываются в пользовательской квоте, но учитываются в storage monitoring.

REQ-MEDIA-001. Изображения проходят проверку MIME и magic bytes, безопасное декодирование
Pillow, удаление metadata и создание WebP variants 320, 800 и 1600 px без увеличения.
Animated image, SVG, архивы и polyglot-файлы запрещены в MVP.

REQ-MEDIA-002. Видео проверяется `ffprobe` с timeout/resource limits и транскодируется
worker в MP4 H.264/AAC, максимум 1280×720, 30 fps; создаётся poster. Исходник не становится
доступен студенту.

REQ-MEDIA-003. Upload проходит `pending` → `processing` → `ready` либо `rejected`.
Только `ready` asset можно связать с published revision. Ошибка обработки видна оператору
и не маскируется повторной выдачей старого статуса. Для video job backend отдаёт durable
`phase` и монотонный progress `0..100`; завершение всегда фиксирует `100`.

REQ-MEDIA-004. Download производится через короткоживущий presigned URL или backend proxy
после авторизации. MinIO bucket никогда не становится public.

REQ-MEDIA-005. Reservation ограничивается атомарными PostgreSQL-квотами: не более 5
одновременных загрузок пользователя, 100 глобально и 20 новых reservation за 60 секунд
на пользователя по умолчанию. Лимиты настраиваются, но не могут быть отключены. Успешная
reservation, подтверждение и безопасный код отклонения попадают в audit без имени файла,
содержимого или presigned URL.

## Импорт и дедупликация

1. Administrator выбирает registered source, revision и discovered file/entry. Исторический
   URL endpoint остаётся только для совместимости и отклоняет все inactive/denied sources.
2. Backend проверяет роль и source/license policy, разрешает revision в полный commit,
   создаёт durable import job в PostgreSQL и публикует identifier в Dramatiq через Redis.
3. Worker повторно проверяет source status, repository identity и immutable revision, запускает
   ровно один repository adapter и не выполняет MDX, JavaScript, Git hooks или KiCad commands.
4. Результат сохраняется как draft, source relation, provenance и license snapshot. Remote
   images, code, archives и attachments не загружаются.
5. Exact и fuzzy dedup формируют объяснимые candidates с evidence.
6. Editor редактирует draft. Administrator отдельно выбирает merge/attach/create/reject.
7. После разрешения конфликтов administrator публикует revision.

REQ-IMPORT-001. Repository import принимает только относительный POSIX path без пустых,
`.`/`..` и управляющих сегментов. Для Seeed разрешены только `.md`/`.mdx`, для KiCad —
`.kicad_sym`; один файл ограничен 2 MiB и проверяется соответствующим data-only parser.

REQ-IMPORT-002. Создание import job требует `imports.create`, CSRF и стабильный
`Idempotency-Key`. Повтор с тем же ключом возвращает существующий job и не расходует квоту.
Новые job по умолчанию ограничены пятью активными на пользователя, сотней глобально и десятью
отправками за 60 секунд. Проверка квот и insert сериализованы PostgreSQL advisory lock.

REQ-IMPORT-003. Отмена и повтор требуют отдельных `imports.cancel`/`imports.retry`; editor
действует только над собственным job, administrator — над любым. Worker проверяет terminal
`cancelled` перед сохранением результата. Создание, отклонение, отмена, retry и ошибка enqueue
журналируются безопасными кодами без URL, path, содержимого или внутренних исключений.

REQ-DEDUP-001. Exact keys: `(source_id, source_item_id)`, canonical source URL, media SHA-256
и нормализованная пара manufacturer/model. Проверка выполняется под Redis lock и повторяется
в PostgreSQL transaction; correctness не зависит только от Redis.

REQ-DEDUP-002. Fuzzy score использует нормализованные title/model/manufacturer,
характеристики и perceptual image hash. Candidate хранит score, algorithm version и evidence.

Для baseline `fuzzy-v1` PostgreSQL `pg_trgm` выполняет bounded preselection, после чего
application scorer учитывает token similarity, spec fingerprint, text/media hashes и явные
manufacturer/model/spec conflict penalties. Evidence содержит только числовой breakdown и
версии, без raw content; score `>=0.70` считается unresolved high candidate.

REQ-DEDUP-003. Merge никогда не выполняется автоматически. Только administrator создаёт
merge decision, явно выбирает survivor и значения конфликтующих полей. Решение и before/after
snapshot попадают в audit log.

REQ-DEDUP-004. Экран review показывает карточки в двух колонках, итоговый score, числовой
breakdown, совпадения и конфликты. Merge объединяет выбранные поля, attach переносит provenance
и media без выбора полей, create оставляет обе карточки, reject отклоняет совпадение. Backend
проверяет administrator role, CSRF и обе revision непосредственно перед commit.

## Фоновые задачи

REQ-JOB-001. PostgreSQL хранит durable состояние `queued`, `running`, `retrying`, `succeeded`,
`failed` или `cancelled`, номер попытки, лимит попыток, phase/progress, heartbeat и время следующего retry.
Redis является транспортом Dramatiq и не считается источником статуса.

REQ-JOB-002. Actor идемпотентен по стабильному job UUID/idempotency key: повторная доставка не
запускает завершённую или занятую действующей lease задачу. Просроченная lease допускает
повторный claim, transient failure — bounded exponential backoff, validation failure терминален.

REQ-JOB-003. Только administrator видит общий monitor и вручную возвращает `failed` job в
очередь. Mutation требует CSRF и создаёт audit event; teacher и student получают `403`.

REQ-JOB-004. Обычная страница «Загрузка компонентов» показывает editor только собственные
операции, administrator — все. Публичный контракт использует состояния `pending`, `processing`,
`needs_review`, `ready`, `published`, `error`, `cancelled` и не возвращает коды ошибок,
попытки, heartbeat, queue/worker/parser metadata или внутренние метрики.

REQ-JOB-005. Retry требует `imports.retry`, cancel — `imports.cancel`; обе операции повторно
проверяют владельца на backend. Cancel разрешён только для `queued`, `running`, `retrying`,
сохраняется как терминальный `cancelled` и не может быть перезаписан worker.

## Пользовательский интерфейс

REQ-UI-001. Название продукта в интерфейсе — «Справочник электронных компонентов»,
краткое название — «База компонентов Arduino». Демонстрационные названия и слово `Demo`
не отображаются.

REQ-UI-002. Навигация, роли, состояния, действия, ошибки и служебные страницы отображаются
по-русски. Англоязычные внутренние enum, классы, таблицы и API-поля не переименовываются
ради локализации.

REQ-UI-003. Технические идентификаторы ошибок не отображаются даже в административной
диагностике: интерфейс переводит состояния и этапы в понятные русские формулировки, предлагает
безопасное действие и не показывает имена таблиц, хранилищ, очередей или обработчиков.
Проверяемые идентификаторы исходных данных (версия, commit, путь файла) остаются доступными.

REQ-UI-004. Контрактный frontend-тест запрещает возвращение ключевых английских и
демонстрационных строк. Утверждённые светлые и тёмные снимки для desktop/mobile
обновляются явным визуальным запуском.

REQ-UI-005. Шапка показывает имя пользователя и русское название его основной роли в две
строки. Основная и редакционная навигация строится только из permissions, полученных от
backend; название роли используется для представления, но не для решения о доступе.

REQ-UI-006. Ученик видит только пользовательские разделы, редактор — материалы и загрузку
компонентов, администратор дополнительно — управление пользователями и диагностику.
Сервер повторно защищает каждый маршрут независимо от скрытия ссылки на клиенте.

REQ-UI-007. Основная навигация остаётся доступной на узком экране, а редакционные разделы
перестраиваются из боковой колонки в адаптивные группы без горизонтального переполнения.

REQ-UI-008. Выбор оформления открывается одной кнопкой не меньше 40×40 px и содержит варианты
«Светлое», «Тёмное», «Как на устройстве» с согласованными SVG-иконками и явной отметкой
активного варианта. Menu-button имеет доступные названия и поддерживает клавиатуру.

REQ-UI-009. Выбранное оформление сохраняется локально. Вариант «Как на устройстве» применяет
текущую системную цветовую схему и реагирует на её изменение без перезагрузки.

## Комплексная безопасность

- REQ-SEC-001: каждый sensitive route имеет backend role dependency; object ID не расширяет
  видимость. Foreign media/import object возвращается как not found, administrator scope
  задаётся явно.
- REQ-SEC-002: все authenticated mutations, кроме первичного login, требуют session-bound
  double-submit CSRF. Cross-origin Origin/preflight отклоняется, permissive CORS не включается.
- REQ-SEC-003: FastAPI и reverse proxy возвращают CSP, clickjacking, MIME-sniffing, referrer,
  opener и permissions headers; CSP допускает production assets только same-origin.
- REQ-SEC-004: parser сохраняет exact HTTPS allowlist, all-address DNS validation, connection
  pinning, redirect revalidation и decoded response limits; результат всегда draft.
- REQ-SEC-005: media processing отделён от parser egress. `edge` и `data` — internal networks;
  только reverse proxy дополнительно подключён к host-facing `ingress`,
  наружу опубликован только reverse proxy, отдельный parser worker обслуживает `imports`.
- REQ-SEC-006: login принимает только login/password. Текущие роли и permissions вычисляются
  backend из активных grants и возвращаются authenticated API; клиентские query, form, cookie
  и localStorage не могут расширить principal. Editor создаётся только с непросроченным grant
  и безопасной базовой ролью.
- REQ-SEC-007: executable route contract перечисляет точное permission set каждого защищённого
  HTTP method/path, включая подключённые FastAPI routers. Прямой API без разрешения получает
  единый `permission_denied`; object-scoped media/import operations проверяют владельца и
  возвращают одинаковый `404` для отсутствующего и чужого UUID. Не реализованный lifecycle
  action не должен существовать как частичный endpoint.

## Нефункциональные требования

- REQ-NFR-001: frontend — React + TypeScript + Vite; backend — FastAPI + PostgreSQL.
- REQ-NFR-002: фоновые операции parsing и media processing — Redis + Dramatiq worker.
- REQ-NFR-003: Alembic является единственным механизмом DDL; `create_all` в runtime запрещён.
- REQ-NFR-004: все HTTP-ошибки имеют единый envelope
  `{"error":{"code","message","retryable","request_id"}}`; сообщение безопасно и написано
  по-русски, временная ошибка отмечена для повтора, техническая причина журналируется без
  секретов, а неуспешная задача не помечается завершённой.
- REQ-NFR-005: API versioned с `/api/v1`; OpenAPI является контрактом typed frontend client.
- REQ-NFR-006: все timestamps — timezone-aware UTC, отображение локального времени делает UI.
- REQ-NFR-007: критические изменения, публикация и merge имеют immutable audit events.
- REQ-NFR-008: parser, когда будет подключён к общей очереди, сохраняет только draft; retry
  не расширяет его полномочия и никогда не публикует карточку.
- REQ-NFR-009: корпоративный контур работает на Ubuntu Server со static IP и exact internal
  DNS; наружу VM публикует только 80/443, HTTP перенаправляется на проверяемый internal HTTPS,
  а PostgreSQL, Redis и MinIO не получают host ports.

## Поиск и фильтры

- REQ-SEARCH-001: student catalog ищет только неархивированные published revisions активных
  категорий; draft и более новые неопубликованные правки не влияют на результат.
- REQ-SEARCH-002: индексируемые поля ограничены title, aliases, manufacturer, model, summary
  и tags. Teacher notes, hidden solutions, code examples и remote body не индексируются.
- REQ-SEARCH-003: PostgreSQL full-text search является основным механизмом, `pg_trgm` word
  similarity — fallback для опечаток; title/aliases/model/manufacturer ранжируются выше
  summary/tags.
- REQ-SEARCH-004: category и difficulty применяются совместно с query на backend. Query
  нормализуется, имеет длину не более 100 символов, выдача ограничена 100 карточками.
- REQ-SEARCH-005: публикация атомарно создаёт или обновляет поисковый документ, archive
  удаляет его. Изменения схемы и индексов выполняются только Alembic.
- REQ-SEARCH-006: оператор может получить `EXPLAIN ANALYZE` параметризованного bounded query
  через отдельную CLI-команду; диагностический вывод не содержит скрытых полей.

## Критерии приёмки baseline требований

- четыре документа не противоречат друг другу и проходят contract tests;
- три URL и host allowlist зафиксированы;
- роли, поля, категории, медиа-лимиты и state transitions однозначны;
- parser-to-draft, admin-only merge и backend authorization описаны во всех нужных слоях;
- реализация следует этим контрактам, меняет схему только Alembic и не содержит production
  secrets.

## Открытые вопросы перед production-импортом

1. Получить письменное решение правообладателя/колледжа по объёму копирования, хранению
   изображений, кода и обязательной атрибуции для каждого из трёх источников.
2. Проверить robots.txt и условия сайтов непосредственно перед реализацией adapters;
   доступность страницы сама по себе не означает разрешение на scraping.
3. Определить владельца lifecycle локальных аккаунтов и необходимость последующего SSO;
   baseline MVP уже использует opaque server-side sessions.
4. Утвердить storage budget, retention originals/quarantine и срок хранения audit events.
5. Уточнить, должны ли проекты быть отдельной сущностью; в baseline импорт проекта создаёт
   draft компонентов-кандидатов, а не карточку проекта.
