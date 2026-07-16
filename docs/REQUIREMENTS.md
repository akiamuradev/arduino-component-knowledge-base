# Требования

Статус: утверждаемая baseline-версия этапа 0 от 15 июля 2026 года.

## Назначение и границы

Система предоставляет студентам каталог Arduino-совместимых компонентов, а преподавателям
и администраторам — управляемый процесс создания, импорта, проверки и публикации карточек.
Основной режим эксплуатации — корпоративная сеть колледжа.

В MVP не входят публичная регистрация, публичный SaaS, YouTube, автоматическая публикация,
автоматическое объединение дубликатов и произвольный web crawler.

## Источники импорта

| Код | Пилотный URL | Разрешённый host | Назначение адаптера |
|---|---|---|---|
| `arduino_tex` | <https://arduino-tex.ru/> | `arduino-tex.ru` | Уроки, модули и проекты Arduino |
| `portal_pk` | <https://portal-pk.ru/> | `portal-pk.ru` | Уроки и проекты Arduino |
| `alexgyver` | <https://alexgyver.ru/ardu-proj/> | `alexgyver.ru` | Каталог Arduino-проектов |

REQ-SRC-001. Каждый источник реализуется отдельным versioned adapter. Произвольный URL
не выбирает парсер по содержимому страницы.

REQ-SRC-002. Backend принимает только HTTPS URL с host из allowlist и повторно проверяет
каждый redirect. Credentials, нестандартные порты и URL с неоднозначной canonicalization
отклоняются.

REQ-SRC-003. Источник по умолчанию работает в режиме `metadata_only`. Загрузка и
долговременное хранение исходного текста или binary media включаются администратором
только после фиксации прав, объёма использования и правил атрибуции.

REQ-SRC-004. Успешный parser job всегда создаёт или обновляет `draft`; parser не может
установить `published` и не может объединить компоненты.

REQ-SRC-005. Для каждой импортированной карточки сохраняются source URL, canonical URL,
время получения, adapter/version, source identifier при наличии, content hash и атрибуция.

REQ-SRC-006. Первым реализован `arduino-tex.ru` adapter для `/news/{id}/{slug}.html`.
Его versioned fixture проверяет DOM contract; результат содержит только metadata/plain text,
имеет `status=draft` и `source_policy=metadata_only`. Revision `20260716_08` сохраняет этот
результат как draft и source provenance через durable import job.

REQ-SRC-007. Fetcher повторно разрешает все A/AAAA для initial URL и каждого redirect,
отклоняет запрос, если хотя бы один адрес non-global, и подключается к выбранному проверенному
IP с исходными Host/SNI и TLS verification. System proxy, cookies, credentials и automatic
redirects запрещены; decoded HTML ограничен 2 MiB, headers — 32 KiB, redirects — тремя.

REQ-SRC-008. `portal-pk.ru` использует отдельный adapter v1 для `/news/{id}-{slug}.html`,
а `alexgyver.ru` — отдельный adapter v1 для detail page `/{project}/`; индекс
`/ardu-proj/` не считается карточкой компонента. Оба возвращают тот же metadata-only draft
contract и не импортируют article body, downloads, scripts или media.

REQ-SRC-009. Parser drift возвращает bounded diagnostic с typed code, source host,
parser name/version и logical field. Raw HTML, URL query, remote text и внутренний traceback
в diagnostic не включаются; отсутствие и неоднозначность обязательных metadata различаются.

## Роли и авторизация

Роли являются backend enum и назначаются администратором. Frontend скрывает недоступные
действия только для удобства; окончательное решение всегда принимает backend.

| Действие | `student` | `teacher` | `administrator` |
|---|:---:|:---:|:---:|
| Читать опубликованный каталог и разрешённые медиа | Да | Да | Да |
| Читать draft и историю импорта | Нет | Да | Да |
| Создавать и редактировать draft вручную | Нет | Да | Да |
| Запускать parser для allowlisted URL | Нет | Да | Да |
| Загружать медиа в quarantine | Нет | Да | Да |
| Публиковать проверенный draft без merge-конфликта | Нет | Да | Да |
| Предлагать решение по дубликату | Нет | Да | Да |
| Подтверждать или отклонять duplicate merge | Нет | Нет | Да |
| Управлять пользователями, ролями, источниками и категориями | Нет | Нет | Да |
| Читать security audit | Нет | Нет | Да |

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

## Карточка компонента

### Идентификация и жизненный цикл

- `id`: UUID, immutable;
- `slug`: уникальный стабильный URL key;
- `status`: `draft`, `published` или `archived`;
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

## Импорт и дедупликация

1. Teacher отправляет один URL через backend.
2. Backend валидирует роль, source policy и URL, создаёт durable import job в PostgreSQL
   и публикует его identifier в Dramatiq через Redis.
3. Worker повторно валидирует target, запускает ровно один source adapter и нормализует
   данные без исполнения remote HTML/JavaScript.
4. Результат сохраняется как draft и source record; media candidates остаются ссылками
   либо попадают в quarantine согласно source policy.
5. Exact и fuzzy dedup формируют объяснимые candidates с evidence.
6. Teacher редактирует draft. Administrator отдельно подтверждает merge/reject.
7. После разрешения конфликтов teacher или administrator публикует revision.

REQ-DEDUP-001. Exact keys: `(source_id, source_item_id)`, canonical source URL, media SHA-256
и нормализованная пара manufacturer/model. Проверка выполняется под Redis lock и повторяется
в PostgreSQL transaction; correctness не зависит только от Redis.

REQ-DEDUP-002. Fuzzy score использует нормализованные title/model/manufacturer,
характеристики и perceptual image hash. Candidate хранит score, algorithm version и evidence.

REQ-DEDUP-003. Merge никогда не выполняется автоматически. Только administrator создаёт
merge decision, явно выбирает survivor и значения конфликтующих полей. Решение и before/after
snapshot попадают в audit log.

## Фоновые задачи

REQ-JOB-001. PostgreSQL хранит durable состояние `queued`, `running`, `retrying`, `succeeded`
или `failed`, номер попытки, лимит попыток, phase/progress, heartbeat и время следующего retry.
Redis является транспортом Dramatiq и не считается источником статуса.

REQ-JOB-002. Actor идемпотентен по стабильному job UUID/idempotency key: повторная доставка не
запускает завершённую или занятую действующей lease задачу. Просроченная lease допускает
повторный claim, transient failure — bounded exponential backoff, validation failure терминален.

REQ-JOB-003. Только administrator видит общий monitor и вручную возвращает `failed` job в
очередь. Mutation требует CSRF и создаёт audit event; teacher и student получают `403`.

## Нефункциональные требования

- REQ-NFR-001: frontend — React + TypeScript + Vite; backend — FastAPI + PostgreSQL.
- REQ-NFR-002: фоновые операции parsing и media processing — Redis + Dramatiq worker.
- REQ-NFR-003: Alembic является единственным механизмом DDL; `create_all` в runtime запрещён.
- REQ-NFR-004: ошибки имеют typed code, request/job ID и безопасное сообщение; исключения
  логируются без секретов, а failed job не помечается successful.
- REQ-NFR-005: API versioned с `/api/v1`; OpenAPI является контрактом typed frontend client.
- REQ-NFR-006: все timestamps — timezone-aware UTC, отображение локального времени делает UI.
- REQ-NFR-007: критические изменения, публикация и merge имеют immutable audit events.
- REQ-NFR-008: parser, когда будет подключён к общей очереди, сохраняет только draft; retry
  не расширяет его полномочия и никогда не публикует карточку.

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
