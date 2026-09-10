# Архитектурный аудит ACKB

Дата: 2026-09-09. Checkpoint 1 завершён; начаты точечные исправления baseline и CP2.

### Прогресс после аудита

- A3: фиксированный светлый цвет OLED pin labels заменён theme-aware token;
  responsive accessibility scenario прошёл в обеих темах.
- A1: login/register/logout используют общий session-cache transition с cancellation
  до очистки. Query 401 удаляет private cache и обновляет auth state; 403 не завершает
  сессию. Добавлены tests identity switch, late query response, logout и expiry.
- После исправлений frontend lint/typecheck/unit/build и полный обязательный
  Playwright suite прошли; opt-in обновление скриншотов не запускалось.
- A2 SQL isolation: fault injection на отдельном PostgreSQL 17 воспроизвёл aborted
  outer transaction до исправления. Worker bridge теперь использует savepoint и
  явный rollback при FAILED, поскольку runtime поглощает исключение. Проверены
  SQL/ORM flush/logical failures и success; исходные idempotency tests сохранены.
  Это не решает отдельно длительность транзакции и согласование lease/timeout.
- CI после первого push выявил известные уязвимости httpx2/httpcore2 2.7.0.
  Обновлены только эти пакеты до 2.12.0 и связанные lock metadata; минимальная версия
  httpx2 повышена до 2.12. Strict pip-audit runtime lock теперь проходит, backend
  regression/static/smoke и PostgreSQL shadow integration повторно прошли.
- A5 catalog reads: public snapshots/media и workspace collections/sources/media
  загружаются пакетно без изменения visibility или API. PostgreSQL regression
  фиксирует 6 запросов для public page и 10 для workspace page из трёх карточек
  с изображениями; `_data` читает подсказки всех примеров одним join-запросом.
- Ниже сохранены исходные findings, чтобы не терять причины изменений. Checkpoints
  CP3–CP6 целиком ещё не завершены: commands, lease/timeout и полный эксплуатационный
  verification остаются в плане; SQL isolation и read batching уже выполнены.
Основа: main `583d83946752bdb820abd03ea088746ec6ad1561` и незакоммиченный
frontend branding WIP. Выводы о WIP нельзя автоматически относить к main.
Изменения с другого компьютера в доступном origin/main не обнаружены.

## Карта исследования — не перечитывать без нового вопроса

Полная структурная инвентаризация: 142 Python-модуля приложения, 30 803 строки,
73 Python-файла тестов, 28 миграций. AST-скан импортов и одинаковых тел функций
выполнен для всех Python-модулей приложения. Это не построчная проверка каждого файла.

Прочитаны полностью: main.py, db.py, api/dependencies.py, errors.py, security.py,
logging.py, broker.py, worker.py, imports/tasks.py, dispatch/reconciler.py,
tests/conftest.py, pyproject.toml, .github/workflows/quality.yml, compose.yaml;
frontend: api/client.ts (1–200), workspace/queries.ts, imports/review-queries.ts,
auth/queries.ts, app/query-client.ts. Из предыдущего исследования известны
CatalogPage, HardwareBoard, branding, MediaGallery, AppHeader/StudentLayout и CSS;
статус тестов WIP приведён ниже отдельно от main.

Целевые участки прочитаны: catalog/service.py (list_published, transition, _data,
_card), api/catalog.py (public response/list, transitions), auth/service.py
(register, authenticate, reset_password, create_administrator, set_roles,
disable_user), auth/domain.py (roles/permissions), dispatch/repository.py (1–205),
imports/processor.py (до основной persistence-ветки), pipeline/worker_shadow.py.
Дополнительно изучены runtime/persistence/import review, media service/repository/
processors/storage/retention, auth/passwords, health, migrations/env, config validators,
production overlay (identities/grants/networks), nginx routes/TLS/headers/body limits,
Dockerfile, production_preflight, clean-stack isolation, backup/restore runbook.
Frontend: editor mapping/save, users/admin forms, query invalidation и eager routes.
Tests: inventory, baseline execution, auth/admin boundary tests, pipeline PostgreSQL
idempotency test, frontend e2e failure. Документация: ARCHITECTURE, THREAT_MODEL,
целевые разделы SECURITY/DEPLOYMENT/OPERATIONS. Не все перечисленные крупные файлы
прочитаны построчно: изучены участки, относящиеся к проверяемым runtime-контрактам.

## Уже подтверждено

- Modular monolith, отдельные процессы API / media worker / parser worker /
  dispatch reconciler. PostgreSQL — источник истины jobs; Redis — доставка и locks;
  MinIO — закрытые quarantine/variants. Не нужны microservices или новый bus.
- CatalogService (1810 строк) совмещает lifecycle, snapshots/search, media,
  corrections, merge duplicates и чтение DTO. Нужны осмысленные внутренние границы,
  а не repository для каждой таблицы.
- Исходные list_published/_data делали per-card/per-hint запросы. После аудита
  добавлены PostgreSQL query budgets и пакетное чтение public/workspace страниц;
  latency отдельно не измерялась.
- API catalog/imports совмещают schemas, projections, assembly и transactions.
- Principal объединяет application identity/permissions с session_id/csrf_hash;
  будущая auth boundary может разделить эти обязанности без SSO сейчас.
- broker.py создаёт Settings и broker при импорте. reconciler создаёт и уничтожает
  Database на каждой итерации; сохранить per-message loop safety у Dramatiq.
- imports/processor.py запускает legacy persistence и опциональный shadow pipeline
  внутри блокировки/транзакции. Pipeline сейчас не является единственным рабочим
  путём: удалять legacy по имени нельзя.
- AST подтвердил повторение JSON field readers в восьми pipeline/models файлах,
  _safe_value_code в API/worker и _library_name в adapter/index.
- Domain->HTTP импортов не найдено (кроме ожидаемого composition root main.py).
  Есть зависимости catalog↔media, catalog↔deduplication, imports↔dispatch на уровне
  пакетов; это ещё не доказательство циклической ошибки импорта при запуске.
- CI уже содержит backend/frontend/e2e/integration/containers и общий gate,
  clean-stack, recovery и production identity проверки. Их нужно сохранять.

## 1. Current architecture map

```text
Browser: React / Router / React Query / API client
  → nginx reverse proxy
      → frontend nginx: Vite assets
      → FastAPI: auth/catalog/admin/imports/review/media/jobs
      → MinIO: signed upload/download routes

FastAPI / application operations → PostgreSQL
  identity / sessions / throttles / audit
  components / revisions / snapshots / search / corrections / duplicates
  imports / evidence / review / media metadata / jobs / dispatch

PostgreSQL dispatch → reconciler → Redis / Dramatiq
  → parser-worker: acquisition / parsing / draft persistence
  → media worker: image/video processing / MinIO variants
  → PostgreSQL: attempts / leases / progress / terminal state
```

PostgreSQL — источник истины, включая jobs. Redis — доставка и временные locks,
не единственное хранилище заданий. Auth throttling реализован через PostgreSQL.
MinIO содержит закрытые quarantine/variants с временными подписанными URL.
Composition root — main.py; session создаётся на request, commit часто в handlers.
Workers используют короткие claim/finish transactions, но shadow-импорт выполняется
внутри финальной транзакции основного импорта.

Ключевые потоки:

- Credentials → session/CSRF → Principal → permissions. Public registration назначает
  student сервером, administrator создаётся отдельной защищённой операцией.
- Draft → review/approval/publication с revision checks, immutable snapshot и search.
  Published read не должен превращаться в чтение произвольного текущего draft.
- Import admission → persisted job/dispatch → acquisition/adapters → draft.
  Evidence-first runtime работает опционально как shadow. Review confirmation
  не равен публикации компонента.
- Media reservation, в том числе до draft save → upload → ownership/confirmation
  → job → variants → attach/publication/retention.

## 2. Strong parts / KEEP

| Элемент | Решение и основание |
| --- | --- |
| Modular monolith и весь текущий стек | KEEP: соответствует текущим задачам; новые сервисы/framework не нужны |
| Argon2id, sessions, CSRF, permissions | KEEP: менять ownership кода, не правила доступа |
| Last active administrator protection | KEEP: блокировки и конкурентные проверки обязательны |
| Lifecycle/revisions/snapshots | KEEP: основа воспроизводимости и контроля публикации |
| Provenance/licensing/pipeline contracts | KEEP: предметная сложность, не boilerplate |
| Durable dispatch/recovery | KEEP: не заменять прямым enqueue после commit или Redis-only jobs |
| MediaStorage, private buckets, FFmpeg limits | KEEP: полезные внешние границы и security controls |
| Alembic, pinned images/locks, production validators | KEEP: не squash-ить миграции ради косметики |
| CI backend/frontend/integration/containers gate | KEEP: уже существенный safety net |
| Workbench/branding/HardwareBoard/themes/lightbox/OLED | KEEP: текущая UX-база, нового redesign не требуется |

Размер pure policy-файла сам по себе не причина дробления: matcher/extractor/quality
разделять только по реальной ответственности, а не по лимиту строк.

## 3. Architectural problems

P1 — исправить до расширения рефакторинга; P2 — ближайшие управляемые этапы;
P3 — локальная уборка после фиксации поведения. Это приоритет работ, не CVSS.
Backend paths ниже относительны к `src/arduino_component_kb/`.

| ID / класс | Где и конкретная проблема | Эффект исправления / риск |
| --- | --- | --- |
| A1 P1 REFACTOR | `frontend/src/components/AppHeader.tsx:19`, LoginPage/RegisterPage, app/query-client: logout удаляет только current-user query; остальные keys не привязаны к identity | Устранить остаточные данные между сессиями SPA. Сохранение кэша подтверждено кодом; показ чужих данных требует regression scenario, это не обход backend RBAC. Cancel/clear при identity transition; риск позднего ответа старого запроса |
| A2 P1 REFACTOR | `imports/processor.py:203`, pipeline/worker_shadow, `pipeline/runtime.py:214`: shadow использует ту же SQL session/transaction, runtime превращает исключение в FAILED, savepoint отсутствует | SQL failure может оставить общую транзакцию aborted и сорвать legacy import. Риск выведен из кода, fault injection ещё нужен. Изолировать SQL shadow; catch без rollback недостаточен. Риск изменения atomicity/idempotency |
| A3 P1 REFACTOR, WIP | styles.css/OledLoginDisplay; Playwright login at 320px падает на `.oled-pins > span` | Воспроизведён контраст 1.29:1 вместо 4.5:1. Точечный fix baseline, не redesign. Риск затронуть обе темы/mobile |
| A4 P2 REFACTOR / MOVE, PARTIAL | catalog/service остаётся крупным: reads/media/search/dedup и низкоуровневые mutations; lifecycle transaction coordination вынесена в catalog/operations, HTTP больше не владеет lifecycle audit/commit | Дальше отделять только осмысленные операции. Snapshot visibility, locking и revision/audit order защищены тестами; массовый split не нужен |
| A5 P2 REFACTOR, DONE | catalog/service list_published, list_cards, _data, snapshots; media/repository variants | Public list использует 6, workspace list — 10 запросов для трёх карточек с media без per-card роста. Snapshot/current-draft пути остаются раздельными; порядок и payload покрыты regression tests. Latency не измерялась |
| A6 P2 MOVE / REFACTOR, PARTIAL | Lifecycle workflow перенесён из catalog handlers; api/imports admission/commit и часть других catalog writes ещё координируются в HTTP; auth/repository audit используется другими доменами | Следующими переносить только доказанные workflow и выделить узкий audit writer с session вызывающего кода. Не откатить failure audit/throttle, которые намеренно сохраняются при отказе |
| A7 P2 REFACTOR | broker, dispatch/reconciler, db, api/dependencies | Broker/Settings при import; engine пересоздаётся каждый reconcile cycle; DatabaseGateway не описывает используемые sessions. Явный resource lifetime. Риск переиспользовать async pool между разными asyncio.run у Dramatiq |
| A8 P2 REFACTOR | auth/passwords и async auth/service вызывают синхронный Argon2 hash/verify | CPU work занимает event loop; нагрузочный эффект не измерен. Bounded thread offload, без ослабления Argon2. Риск роста памяти при неограниченной конкурентности и нарушения dummy verify |
| A9 P2 MOVE / REFACTOR | ComponentEditorPage, user/admin pages, workspace/import review queries | Смешаны mapping/form/server state/mutations/invalidation. Pure editor mapping и domain query ownership. Риск потери незавершённого draft и staged photos |
| A10 P2 MERGE | pipeline/models readers, _safe_value_code API/processor, _library_name adapter/index | AST подтвердил одинаковые тела. Небольшие helpers вместо расхождений; риск nullable/error semantics и persisted payload compatibility |
| A11 P2 REFACTOR docs | ARCHITECTURE/THREAT_MODEL против handlers/compose | Обещаются отсутствие SQL в routes и отсутствие backend egress — фактически неверно. Исправить описание, не отключать нужную сеть вслепую |

## 4. Coupling and dependency problems

Domain/service → HTTP imports не обнаружены, кроме ожидаемого composition root.
Есть взаимные зависимости пакетов, не обязательно runtime import errors:

- catalog ↔ media: runtime-вызов MediaService → CatalogService удалён; media получает
  узкий ComponentAttachmentWriter при сборке API. Catalog по-прежнему читает media и
  управляет связями, а MediaRepository использует Component для optimistic lock/quotas,
  поэтому persistence coupling остаётся явным.
- catalog ↔ dedup: duplicate review вызывает catalog, catalog знает duplicate ORM.
- imports ↔ dispatch; dispatch → worker: delivery contracts связаны с actor startup.
- catalog/media → AuthRepository ради общего audit.

Цель: HTTP → operation; catalog владеет component mutations; media — assets/ownership;
dedup review оркестрирует catalog operation; dispatch publisher собирается на границе
процесса. Не нужны protocol/DTO для каждой функции или generic repository на таблицу.

## 5. Backend findings

Catalog: сначала отделить чтение и пакетную сборку, потом write operations.
SQLAlchemy в application queries допустим: проблема в скрытых запросах и commit
ownership, не в самом ORM. `_data` читает hints для каждого example; published
card/media projections добавляют per-card work. Workspace и published reads
сохранять раздельными по семантике, даже при общих batch helpers.

Transactions: один явный владелец операции, но не универсальный commit-on-success.
Auth failures, import admission rejection и durable media rejection могут сохранять
состояние при ошибочном HTTP ответе. Audit writer не должен независимо коммитить.

Import runtime: acquisition → extraction → normalization → identity → enrichment
→ evaluation → composition → persistence. Не переделывать предметную последовательность
ради пяти красивых слоёв. Shadow добавляет работу под финальной блокировкой;
heartbeat перед входом не равен продлению lease на всём протяжении работы.
Проверить elapsed time/Redis TTL/re-delivery. `asyncio.timeout` не прерывает
синхронный CPU-bound parser. SAVEPOINT решает SQL isolation, но не длительность
транзакции. Не переключать весь импорт на pipeline в рамках такого исправления.

Media уже разделяет storage/processing/metadata/retention. В image processor
повторяются блоки retry/terminal failure: MERGE локальный helper, не job framework.
SQL и object storage не имеют общей транзакции; сохранить retention grace/bounds,
referenced-key checks и recovery semantics.

Auth future-proofing: application actor (user/roles/permissions) отделить от
session credentials/CSRF/expiry только по мере переноса операций. Сохранить users,
permission helpers и local bootstrap. OIDC/LDAP/passkeys/recovery сейчас не внедрять.

## 6. Frontend findings

A1: нужен один владелец identity transition для login/register/logout/session expiry,
включая отмену старых запросов. UI permission guards сохранять: UX-проверка и backend
enforcement имеют разные задачи, это не вредное дублирование.

ComponentEditorPage (~734 строки) владеет mapping, workingCard, imagesDirty,
permissions, lifecycle/history. Минимальное извлечение: emptyState/stateFromCard/
toDraftInput в pure editor-state с round-trip tests. Затем invalidation после
save/transition; refetch не должен перезаписывать несохранённый текст, а загрузка
фотографий не должна зависеть от сохранения draft.

Query modules уже есть — развить их вместо новой state library. Review mutation
инвалидирует общий prefix, затем detail под тем же prefix — избыточно. Workspace,
catalog, review и users имеют независимые invalidation paths при связанных данных:
составить mutation → affected queries contract и tests, не утверждать, что каждый
независимый ключ обязательно является дефектом.

API client/contracts централизованы — KEEP. `body as T` не проверяет фактический
ответ; добавить точечные контрактные tests API/fixtures, не валидатор каждого
поля формы. Password confirmation и серверные password rules имеют разные задачи.

Routes eagerly import admin/editor pages. Build JS 528.73 kB, gzip 151.47 kB,
warning >500 kB: P3 lazy route boundaries после измерения загрузки. Catalog search
запрашивает данные при изменении текста: оценить debounce/cancellation. API list
имеет limit, клиентской полноценной пагинации нет — ограничение роста, не повод
добавлять новый product workflow в этом рефакторинге.

CSS WIP: mobile brand-mark имеет правила 68px и более позднее 84px; проверить каскад.
Записываемые --board-px/--board-py и --blob-x/--blob-y больше не используются через
var(): кандидаты DELETE. React logo glyphs и standalone SVG повторяются — единый
источник/проверка синхронности, не новый framework. Не делать массовую замену CSS.

## 7. Infrastructure findings

KEEP: production fail-closed Settings, dedicated PostgreSQL runtime/backup identities,
MinIO scoped policy, pinned images/locks, TLS/CA verification, read-only/tmpfs/cap-drop.
28 миграций и runtime grants — совместный контракт; перенос Python без изменения
schema не требует новой Alembic migration.

Backend подключён к parser-egress; production overlay это не исключает. Документация
no-egress неверна. Сначала описать preview/acquisition needs; перенос сетевой работы
в worker — отдельное решение с сохранением HTTP-контракта, не косметика сети.

Base port `${ACKB_HTTP_PORT:-8080}:8080` опубликован на всех интерфейсах, не только
localhost. Production binding/TLS отдельные. Не менять LAN-доступ вслепую.

PID health workers/reconciler не доказывает обработку jobs. `/ready` проверяет PG,
не весь Redis/MinIO pipeline: допустимо для каталога, но не «все сервисы исправны».
Уточнить runbook и проверки прогресса, не связывать доступность каталога со всеми queues.
Parser-worker concurrency/resource budget менее явный, чем media worker: измерить
RAM/threads/processes/tmpfs и lease на максимальном разрешённом входе до новых limits.

nginx общий body limit 260m нужен media и не является auth throttling. Proxy
перезаписывает forwarded headers; backend доверяет proxy внутри контейнерной границы.
Сохранить отсутствие публичного backend port. Security headers повторены в nginx
и Python: контракт совпадения полезнее удаления защиты на одном пути вслепую.

OPERATIONS описывает согласованный PG/MinIO backup с остановкой writers, off-host
хранением и restore drill — KEEP. Clean-stack script использует отдельный random
project/port/volumes; в этом аудите он не запускался. Рабочий localhost не останавливали.

## 8. Testing findings и фактический baseline

| Проверка текущего worktree | Результат |
| --- | --- |
| Ruff check / format | PASS; 257 файлов форматированы |
| mypy strict src/scripts/tests/migrations | PASS; 257 source files |
| pytest без integration | PASS; integration исключены |
| docs_contract / release_contract / backend_smoke | PASS; version contract 1.0.1 |
| Frontend lint / typecheck | PASS |
| Frontend unit | PASS |
| Production build в e2e script | PASS; bundle-size warning |
| Playwright на момент аудита | FAIL из-за A3; opt-in screenshots пропущены |
| docker compose config --quiet | PASS для base configuration |

Не запускались: real-service integration, clean install/restore drill, production
preflight с реальными TLS/secrets, rebuild всех контейнеров, отдельный package build,
новые dependency vulnerability scans. Их наличие в CI не равно локальному PASS.
Backend smoke не заменяет настоящие PG/Redis/MinIO проверки.

Frontend e2e с API fixtures проверяет UI, не полную согласованность live backend.
Приоритетные новые regression cases:

- identity switch + delayed response + logout/session expiry;
- SQL failure внутри shadow: legacy result, rollback, retry, no duplicates;
- query count при росте списка и snapshot visibility;
- stale revision, last-admin race, session revocation, durable failure audit;
- partial draft + staged images + save/transition invalidation;
- timeout/lease/re-delivery и terminal-state stability.

Settings/principal factories повторяются в auth/catalog/security/media tests.
MERGE только одинаковые defaults, оставляя scenario overrides явно. Уже существует
tests/import_pipeline_helpers.py — не создавать второй helper layer. Handler tests
с mocked services сохранять, дополняя реальными HTTP/DB boundaries при переносе операций.
Integration opt-in не гарантирует безопасную DATABASE_URL: guard или изолированный
Compose project обязателен перед расширением локальных DB drills.

## 9. Dead/legacy code findings

| Элемент | Класс и условие |
| --- | --- |
| api/dependencies.py require_roles | DELETE: usages в src/tests не найдены; действующие permission helpers сохранить |
| pipeline/orchestration.py PipelineOrchestrator | DELETE после переноса полезных order-contract tests: unwired skeleton, реальный runtime другой |
| Pipeline JSON readers | MERGE: 8 required-string, 6 optional-string, 5 required-int и другие совпадения; сохранить error semantics |
| _safe_value_code / _library_name | MERGE в ближайший владеющий пакет, не глобальный misc/utils |
| CSS variables без consumers | DELETE после responsive/theme verification; относится к WIP |
| SplatEmptyState | MOVE/rename при необходимости: компонент используется, старое имя не означает dead code |
| Legacy adapters/composition mapper | KEEP: mapper вызывается shadow comparison, adapters остаются runtime path |
| Snapshot legacy keys/error envelope compatibility | KEEP до проверки реальных persisted data/clients, не удалять по возрасту |

Нет основания массово удалять tests, migrations, provenance/license материалы.
Отсутствие внутренних вызовов требует проверки exports/CLI, не автоматического удаления.

## 10. Security-sensitive areas

Сохранить: student-only registration, server-owned administrator role, permissions,
Argon2id, revocation, CSRF/throttles, last-admin locking, safe audit, revision conflicts,
published visibility, licensing/provenance, staged media ownership, acquisition
SSRF/type/size/time bounds, private buckets, durable jobs/idempotency.

A1 — риск остаточных данных браузера; A2 — целостности/доступности импорта;
A8 — доступности под нагрузкой. Это не доказательство утечки credentials или обхода
administrator permissions. Fault-injection/load checks ещё нужны. Safe error envelope,
request IDs и allowlisted structured logging сохранять.

## 11. Proposed target architecture

| Владелец в существующем monolith | Ответственность |
| --- | --- |
| main / process entrypoints | Settings/resources/broker/publisher startup/shutdown |
| API | Request validation, auth/permissions, вызов операции, HTTP projection |
| auth | Credentials/sessions и существующая identity/RBAC policy |
| Небольшой audit writer | Безопасное событие в session вызывающей операции |
| catalog queries | Batch reads, published snapshots отдельно от workspace |
| catalog operations | Component lifecycle/revisions/mutations и transaction coordination |
| media | Reservation/ownership/assets/variants/processing/retention |
| imports | Admission/acquisition/adapters/runtime/review/draft persistence |
| dispatch | Durable delivery/claim/reconcile; transport adapter на границе процесса |
| frontend auth transition | Lifetime пользовательского кэша |
| frontend domain queries | Keys/mutations/invalidation; pages компонуют экран |
| frontend editor state | Pure mapping и локальный несохранённый form state |

Создавать файлы только при извлечении реальной ответственности. Не нужен слой
Controller → Service → Manager → Repository. Разделение catalog reads/operations —
организация кода внутри пакета, не внедрение CQRS. Не держать старую и новую
реализацию после переноса; не добавлять ненужные compatibility layers.

## 12. Refactor order / staged implementation plan

Каждый подпункт — небольшой самостоятельный commit: characterization test →
исправление/перенос → удаление заменённого пути. Не смешивать массовый rename
с изменением поведения. Аудит сам по себе не повышает версию и не является release.

| Этап | Минимальный объём / эффект | Приёмка, риск и меньшая альтернатива |
| --- | --- | --- |
| 0. Baseline | Отдельно закончить branding WIP, исправить A3 без redesign | UI suite зелёный, обе темы/mobile/gallery; не смешивать с backend refactor |
| 1a. CP2 foundations | A1: единый identity transition, cancel/clear sensitive cache | Admin → student + delayed response не оставляют старых данных; меньше полного key redesign |
| 1b. CP2 ownership | Sessions contract, reconciler resource lifetime, audit writer, commit ownership | Auth/error/dispatch и failure audit tests; broker factory только для реального import coupling, не новый DI |
| 2a. CP3 shadow | Fault injection A2 → SQL isolation; отдельно long transaction/lease | Shadow failure не портит legacy result, retry без duplicates; не переключать весь pipeline |
| 2b. CP3 reads — DONE | Query assembly/batching A4/A5 без изменения writes | PostgreSQL budgets фиксируют public/workspace query count; payloads/visibility сохранены, writes не менялись |
| 2c. CP3 commands — DONE | Lifecycle mutations, revision-aligned audit и commit/rollback координирует catalog/operations; media использует внедрённый ComponentAttachmentWriter без обратного вызова CatalogService | Unit/API regression: revisions, audit metadata/request ID, rollback и media ownership; полный backend suite. Corrections/dedup и остальные writes намеренно не переписывались |
| 2d. CP3 workers/auth | Убрать повтор failure handling, bounded Argon2 offload | Concurrency/memory/lease checks; per-message engine сохранить при разных event loops |
| 3. CP4 frontend | Pure editor state, domain invalidation, users query ownership, точечный CSS cleanup | Draft/photos/admin workflows/e2e стабильны; lazy routes отдельно и после измерений |
| 4. CP5 consistency | Merge readers/helpers, удалить unwired skeleton/require_roles, общие реальные fixtures | Persisted compatibility и behavioral coverage не снижены; active legacy adapters не трогать |
| 5. CP6 hardening | Docs по факту + полный local/CI pass + isolated clean stack | Package/build/smoke/audits, fresh migrations, PG/Redis/MinIO/workers/reconciler/proxy, production/TLS contracts, restore drill |

Перед шагом фиксировать: какую проблему решаем; какой coupling удаляем; почему
проще; какие tests защищают поведение; возможна ли меньшая правка. Обновлять только
реально затронутые docs и эту карту, не создавать историю release-report файлов.

## 13. Risk assessment

Высокий риск: перенос publication/auth/import/media transactions. Сохранить lock
order, expected revisions, durable failure records и atomic audit; сначала реальные
PostgreSQL tests в изолированной среде, затем перенос операции.

Средний: read batching, cache lifecycle, executor lifetime, form state. Сравнивать
payload/query count/delayed responses/незавершённые drafts. Низкий: proven-dead helpers
и docs после проверки references/exports. Массовые переименования ради стиля исключены.

Откат — небольшими commits без необязательных schema migrations, а не содержанием
двух архитектур одновременно. Не запускать restore/cleanup/integration против
неизвестной или рабочей БД. Остановить перенос, если нельзя доказать сохранение RBAC,
snapshot visibility, licensing или ownership.

Это архитектурный аудит, не построчная security-проверка каждого файла, penetration
test или certification production. Не утверждается, что все дефекты найдены.
CP2 начат с A1, A3 исправлен; checkpoints 3–6 ещё не выполнены.
Следующие backend шаги — query-count
baseline и batching каталога; длительность shadow/lease остаётся отдельной задачей.

Для продолжения не перечитывать изученные участки без нового вопроса/изменения файла.
Читать только изменяемую функцию и её непосредственные contracts/tests. Остались
динамические проверки identity switch, SQL failure isolation/query count, load/leases,
clean install и production drills — повторный просмотр кода их не заменит.
