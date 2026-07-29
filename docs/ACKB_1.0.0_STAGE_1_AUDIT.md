# ACKB 1.0.0: аудит перед выпуском

Дата аудита: 2026-07-28.

Ветка: `release/1.0.0`.

Исходный commit: `546dc20118d04a95bdff5a96af770b280b16bc64`.

Текущая версия приложения: `0.21.0`.

Область проверки: исходный код backend и frontend, схема и миграции PostgreSQL,
Redis/Dramatiq, MinIO, Docker Compose, CI, тесты, документация и фактическое состояние
локального стенда. Это статический аудит реализации и release-gap analysis, а не
penetration test и не выполненная проверка восстановления из резервной копии.

## Итог

Текущий вариант является рабочей и хорошо защищённой основой, но **не соответствует
целевой модели ACKB 1.0.0**. Выпуск `v1.0.0` блокируют модель прав, жизненный цикл
карточки, отсутствие управления временными редакторами, отсутствие рабочего
backup/restore-процесса и технический пользовательский интерфейс.

Главное расхождение связано с правами:

- сервер действительно определяет права по учётной записи и не доверяет выбору в браузере;
- выбор «Студент / Редакция» на странице входа является только визуальным состоянием;
- в базе существуют только `student`, `teacher`, `administrator`;
- роли `editor` и отдельного слоя разрешений нет;
- `teacher` сейчас является фактическим редактором: может создавать и изменять карточки,
  загружать медиа, запускать обычный импорт, публиковать и архивировать карточки;
- это прямо противоречит зафиксированной модели 1.0.0, где преподаватель только предлагает
  исправления, редактор имеет временные ограниченные права, а публикация относится к
  административному контролю.

Вердикт: продолжать по этапам 2–27 исходного плана. До устранения блокеров ниже версию
на `1.0.0` не менять и тег не создавать.

## 1. Текущая архитектура

### 1.1. Контуры приложения

```text
Браузер
  -> nginx reverse proxy
     -> React/Vite SPA
     -> FastAPI /api/v1
        -> PostgreSQL: пользователи, сессии, карточки, ревизии,
                       задания, метаданные медиа, аудит
        -> Redis/Dramatiq
           -> parser-worker: импорт и разбор источников
           -> worker: изображения и видео
        -> private MinIO: исходные файлы и обработанные варианты
```

PostgreSQL является источником истины. Redis используется как транспорт заданий, а не
как единственное хранилище их состояния. MinIO не публикуется напрямую: клиент получает
ограниченные по времени подписанные URL.

### 1.2. Backend

- `src/arduino_component_kb/main.py`, `config.py`, `database.py` — запуск, настройки,
  подключение к PostgreSQL и сборка приложения.
- `src/arduino_component_kb/api/` — HTTP-контракты входа, каталога, пользователей,
  импорта, проверки импорта, дублей, заданий и медиа.
- `src/arduino_component_kb/auth/` — пользователи, роли, сессии, Argon2id, throttling,
  CSRF и audit events.
- `src/arduino_component_kb/catalog/` — карточки, опубликованные snapshots, ревизии,
  поиск, источники и примеры.
- `src/arduino_component_kb/imports/` — получение источников, адаптеры, восьмиэтапный
  pipeline, review workspace, persistence и фоновые задания.
- `src/arduino_component_kb/media/` — reservation/confirmation upload flow,
  валидация, обработка изображений и видео, варианты и retention.
- `src/arduino_component_kb/deduplication/` — поиск и административное решение дублей.

### 1.3. Frontend

- `frontend/src/app/routes.tsx` — маршруты и разграничение разделов;
- `frontend/src/routing/guards.tsx` — клиентские guards по данным `/auth/me`;
- `frontend/src/pages/` — вход, каталог, редакция, импорт, задания, review и дубли;
- `frontend/src/components/` — шапка, тема, состояния, источники, галерея и редактор медиа;
- `frontend/src/api/` — типизированные контракты и клиент с cookie/CSRF;
- `frontend/src/theme/` и `frontend/src/styles/` — тема, адаптивность и оформление.

Клиентские guards улучшают навигацию, но не являются границей безопасности. Основные
mutation endpoints дополнительно проверяют сессию, роль и CSRF на backend.

### 1.4. Данные и миграции

В репозитории 19 последовательных Alembic-миграций, единственная голова —
`20260723_19`. Локальная база находится на этой голове. Runtime DDL и `create_all`
отсутствуют.

Фактический безопасный агрегированный срез локальной базы:

- 1 активный пользователь, роль `administrator`;
- 12 черновиков и 3 опубликованные карточки;
- 33 audit events;
- 32 успешных и 1 неуспешное import-задание;
- media jobs отсутствуют.

## 2. Вход, пользователи и права

### 2.1. Что уже реализовано правильно

- Публичной регистрации нет; пользователя создаёт администратор.
- Пароли хешируются Argon2id и не возвращаются API.
- Сессии используют случайный непрозрачный токен; в PostgreSQL хранится его хеш.
- Cookie имеет `HttpOnly`, `SameSite=Strict`, а production требует `Secure`.
- Mutation-запросы защищены session-bound double-submit CSRF.
- Есть постоянный throttling входа по пользователю и источнику.
- `/auth/me` возвращает реальное имя и роли из серверной сессии.
- Роли перечитываются из базы; блокировка пользователя или смена ролей отзывает сессии.
- Нельзя снять роль или отключить последнего активного администратора.

Основные файлы:

- `src/arduino_component_kb/auth/domain.py`
- `src/arduino_component_kb/auth/models.py`
- `src/arduino_component_kb/auth/repository.py`
- `src/arduino_component_kb/auth/service.py`
- `src/arduino_component_kb/api/auth.py`
- `src/arduino_component_kb/api/admin.py`
- `src/arduino_component_kb/api/dependencies.py`
- `frontend/src/api/auth.ts`
- `frontend/src/routing/guards.tsx`

### 2.2. Фиктивная часть интерфейса

`frontend/src/pages/LoginPage.tsx` предлагает выбрать «Студент» или «Редакция», но
отправляет на сервер только логин и пароль. Переменная `accessMode` меняет лишь
декоративное OLED-состояние. Тест `frontend/src/pages/LoginPage.test.tsx` прямо
подтверждает, что этот выбор не определяет разрешения.

Выбор необходимо убрать на этапе 4. Роль и доступные разделы должны отображаться только
после ответа сервера.

### 2.3. Расхождение с моделью 1.0.0

| Возможность | Сейчас | Требование 1.0.0 |
|---|---|---|
| Роли | `student`, `teacher`, `administrator` | `student`, `teacher`, временный `editor`, `administrator` |
| Проверка доступа | `require_roles(...)` | централизованные permissions |
| Срок роли редактора | отсутствует | обязательный срок действия |
| Преподаватель меняет карточки | да | нет |
| Преподаватель публикует | да | нет |
| Редактор публикует | роли нет | только при отдельном разрешении |
| Список пользователей | API/UI нет | нужен администратору |
| Повторное включение пользователя | нет | нужно администратору |
| Отзыв отдельного grant | только полная замена набора ролей | нужен управляемый grant/revoke |

Опасные текущие привязки:

- `src/arduino_component_kb/api/catalog.py`: `teacher` и `administrator` создают,
  изменяют, публикуют и архивируют;
- `src/arduino_component_kb/api/media.py`: `teacher` и `administrator` резервируют,
  подтверждают и просматривают редакционные upload assets;
- `src/arduino_component_kb/api/imports.py`: `teacher` и `administrator` запускают
  URL-import; repository workflow дополнительно ограничен администратором;
- `frontend/src/components/AppHeader.tsx` и `frontend/src/app/routes.tsx` считают
  преподавателя редактором.

`tests/test_rbac.py`, `tests/test_security.py` и `frontend/src/app/routes.test.tsx`
закрепляют текущую, а не целевую матрицу. Их нужно менять вместе с моделью прав, иначе
они будут защищать неверное поведение.

## 3. Карточки и жизненный цикл

Текущие состояния: `draft`, `published`, `archived`.

Реализовано:

- создание черновика;
- optimistic revision при изменении;
- публикационная валидация источников, описания, медиа и дублей;
- immutable snapshot опубликованной ревизии;
- изменение уже опубликованной карточки переводит рабочую запись в `draft`, но старая
  опубликованная snapshot остаётся доступной ученику;
- архивирование опубликованной карточки;
- `component_revisions` хранит snapshots и `actor_id`;
- HTTP-операции create/update/publish/archive пишут audit events.

Не реализовано:

- `in_review`;
- `changes_requested`;
- `approved`;
- `hidden`;
- отправка редактором на проверку;
- запрос изменений и подтверждение администратором;
- снятие с публикации как отдельная операция;
- восстановление из архива;
- окончательное удаление администратором;
- API/UI истории изменений и авторства.

Отдельный риск истории: дочерние ревизии связаны с компонентом через
`ON DELETE CASCADE`. До добавления окончательного удаления нужно определить, какие
исторические и audit-записи обязаны сохраняться, и не допустить неявного уничтожения
следов действий.

Основные файлы:

- `src/arduino_component_kb/catalog/domain.py`
- `src/arduino_component_kb/catalog/models.py`
- `src/arduino_component_kb/catalog/service.py`
- `src/arduino_component_kb/api/catalog.py`
- `frontend/src/pages/ComponentEditorPage.tsx`
- `frontend/src/pages/ComponentListPage.tsx`
- `frontend/src/api/contracts.ts`
- `migrations/versions/20260716_06_catalog_domain.py`
- `migrations/versions/20260723_19_component_multiple_images.py`

## 4. Административные и пользовательские страницы

Сейчас доступны:

- каталог, карточка, источники и сведения о приложении — любому вошедшему пользователю;
- редакционная сводка и редактор карточки — преподавателю и администратору;
- monitor заданий, repository import, review импорта и дубли — администратору.

Отсутствуют:

- управление пользователями и временными редакторами;
- интерфейс предложений преподавателя;
- полноценная проверка и согласование карточек по новому lifecycle;
- журнал действий с фильтрами;
- техническая диагностика и системные настройки;
- отдельное подтверждение окончательного удаления;
- понятный пользовательский экран зависших/повторяемых заданий и отмена задания.

Основные файлы:

- `frontend/src/app/routes.tsx`
- `frontend/src/layouts/StudentLayout.tsx`
- `frontend/src/layouts/AdminLayout.tsx`
- `frontend/src/pages/AdminDashboardPage.tsx`
- `frontend/src/pages/AdminImportPage.tsx`
- `frontend/src/pages/AdminJobsPage.tsx`
- `frontend/src/pages/ImportReviewPage.tsx`
- `frontend/src/pages/DuplicateReviewPage.tsx`

## 5. Тема, навигация и пользовательские строки

### 5.1. Тема

`ThemeProvider` корректно хранит выбор в `localStorage`, поддерживает светлую, тёмную и
системную тему и реагирует на `prefers-color-scheme`.

`ThemeToggle` не соответствует плану 1.0.0:

- это три постоянно видимые кнопки вместо одной кнопки с меню;
- используются Unicode-символы `☼`, `☾`, `◐`;
- фактический размер кнопок около 32×32 px, меньше целевых 40×40 px.

Файлы: `frontend/src/components/ThemeToggle.tsx`,
`frontend/src/theme/ThemeProvider.tsx`, `frontend/src/styles/global.css`.

### 5.2. Шапка и навигация

Шапка уже показывает имя и роль из серверной сессии, но:

- бренд сокращён до `Arduino Base`;
- подзаголовок `Component Knowledge Base` остаётся английским;
- доступ к «Редакции» вычисляется по старой паре `teacher/administrator`;
- административная навигация смешивает предметные и технические разделы;
- мобильная навигация требует отдельной приёмки на 320 px.

Файлы: `frontend/src/config/brand.ts`, `frontend/src/components/AppHeader.tsx`,
`frontend/src/layouts/AdminLayout.tsx`, `frontend/index.html`.

### 5.3. Найденные английские и технические строки

Точного текста `Parser Demo` в актуальном интерфейсе нет. Остальные запрошенные термины
и их аналоги присутствуют.

| Файл | Примеры пользовательских строк |
|---|---|
| `AdminDashboardPage.tsx` | `dashboard`, `Dashboard`, `Backend workspace API`, `draft`, `rev.` |
| `AdminJobsPage.tsx` | `administrator`, `PostgreSQL`, `Redis`, `failed`, `successful`, `Import jobs`, `Media jobs`, queue/task IDs, attempts, phase |
| `AdminImportPage.tsx` | `repository`, `revision`, `backend`, `draft`, `preview`, `parser`, `Commit SHA`, raw error codes |
| `ImportReviewPage.tsx` | `Evidence-first import review`, `review`, `revision`, `parser issue`, `identity`, `taxonomy`, `enrichment` |
| `ComponentEditorPage.tsx` | `Backend`, `draft`, `Revision`, raw backend codes |
| `ComponentImagesEditor.tsx` | `MinIO`, `backend`, `metadata`, `revision` |
| `SourcesPage.tsx` | `Parser version`, `Revision policy`, `Attribution`, `repository`, `Backend` |
| `SourceAttributionBlock.tsx` | `Revision`, `Parser`, `Attribution`, `Repository`, `backend` |
| `AboutPage.tsx` | `React`, `FastAPI`, `TypeScript`, `PostgreSQL`, `MinIO`, `Redis`, `Dramatiq`, `workers`, `backend`, `parser`, `repository` |
| `AdminLayout.tsx` | `Review импорта`, `Backend authorizes` |
| `routing/guards.tsx` | `Backend не подтвердил сессию` |

Техническая provenance должна сохраниться для аудита и администратора, но обычному
пользователю нужны русские понятные названия: «источник», «версия источника»,
«обработка», «задание», «не удалось», без инфраструктурных деталей.

### 5.4. Ошибки

Формат ошибок неоднороден:

- большинство API endpoints возвращает `{"detail":{"code":"..."}}`;
- unhandled exception middleware возвращает
  `{"error":{"code":"internal_error","message":"Unexpected server error.","request_id":"..."}}`;
- frontend fallback содержит `API request failed`;
- страницы нередко выводят raw codes (`request_failed`, `revision_conflict`,
  `media_enqueue_failed`) или слова `backend`, `MinIO`, `parser`.

Нужен единый безопасный error contract, таблица русских пользовательских сообщений,
correlation/request ID только в раскрываемой диагностике и понятные empty/loading/retry
состояния.

## 6. Импорт, файлы и фоновые задания

### 6.1. Сильные стороны

- URL и repository imports ограничены зарегистрированными источниками.
- Есть защита от SSRF, проверка DNS/IP, редиректов, протокола и размеров.
- Repository revision фиксируется, пути нормализуются, размеры и время ограничены.
- Jobs имеют idempotency key, число попыток, heartbeat, lease и durable status в PostgreSQL.
- Worker умеет повторять временные ошибки и подбирать просроченный lease.
- Upload идёт напрямую в private MinIO по серверному object key и короткому presigned URL.
- Разрешены только заданные MIME, есть ограничения размера, количества и общей квоты.
- Изображения проверяются по сигнатуре, декодируются с лимитами и перекодируются без
  метаданных; анимация и trailing payload отклоняются.
- Видео проверяется и обрабатывается ограниченным subprocess без shell.
- Публичная карточка получает только проверенные варианты из опубликованной snapshot.
- Retention удаляет просроченные pending/rejected/orphan objects только явным apply-run.

### 6.2. Блокирующие и существенные пробелы

1. Публикация job в Redis происходит после commit PostgreSQL без transactional outbox
   или периодического reconciler.
2. При сбое первичной публикации import/media API возвращает `503`, но durable запись
   остаётся `queued`; без ручной повторной доставки она может зависнуть.
3. Повторная публикация import-job при ошибке явно переводит запись в `failed`, а
   media-job после manual retry остаётся `queued`. Поведение двух очередей расходится.
4. Нет отмены queued/running задания.
5. Не найдены end-to-end тесты отказа Redis и перезапуска worker с восстановлением
   незавершённого задания.
6. Редакторские import/upload endpoints привязаны к `teacher`, а не к целевым permissions.
7. Состояния и ошибки заданий показываются пользователю техническими кодами.

Статус этапа 18: пункты 1–5 закрыты таблицей `job_dispatches` в той же transaction, что
import/media job, и отдельным bounded reconciler. Очистка Redis, broker failure и истёкшая worker
lease покрыты автоматическими тестами; duplicate delivery безопасна благодаря job UUID, row lock
и durable state recheck. Исчерпание delivery attempts становится `failed`, а повтор требует
явного RBAC/CSRF/audit действия.

Основные файлы:

- `src/arduino_component_kb/api/imports.py`
- `src/arduino_component_kb/api/jobs.py`
- `src/arduino_component_kb/api/media.py`
- `src/arduino_component_kb/imports/queue.py`
- `src/arduino_component_kb/imports/repository.py`
- `src/arduino_component_kb/imports/processor.py`
- `src/arduino_component_kb/media/queue.py`
- `src/arduino_component_kb/media/repository.py`
- `src/arduino_component_kb/media/processor.py`
- `src/arduino_component_kb/media/video_processor.py`
- `frontend/src/pages/AdminImportPage.tsx`
- `frontend/src/pages/AdminJobsPage.tsx`
- `frontend/src/components/ComponentImagesEditor.tsx`

## 7. Журналирование

Таблица `audit_events` уже существует и хранит actor, action, object, request ID,
outcome, details и время. Записываются:

- успешные, неуспешные и заблокированные попытки входа;
- выход, создание и блокировка пользователя, смена ролей;
- основные HTTP-изменения карточек;
- операции импорта, review и дублей;
- reservation/confirmation/rejection медиа;
- retry/failure/retention фоновых заданий.

Пробелы:

- нет API и страницы просмотра журнала;
- нет фильтров по времени, пользователю, объекту, действию и результату;
- нет формального retention-периода и процесса архивирования;
- индекс только по времени недостаточен для будущих фильтров;
- созданные worker/import-процессом карточки не гарантируют тот же
  `component.created` event, что HTTP-сценарий;
- нет отдельного пользовательского представления истории карточки;
- перед окончательным удалением нужно закрепить неизменяемость audit trail.

Файлы: `src/arduino_component_kb/auth/models.py`,
`src/arduino_component_kb/auth/repository.py`,
`src/arduino_component_kb/catalog/service.py`,
`src/arduino_component_kb/imports/`, `src/arduino_component_kb/media/`.

## 8. Производственная конфигурация

### 8.1. Что уже есть

- production overlay включает HTTPS и internal TLS;
- PostgreSQL, Redis и MinIO не публикуются наружу;
- образы базовых сервисов закреплены digest;
- секреты не имеют значений по умолчанию и скрыты из `repr`;
- production запрещает insecure session cookie и MinIO без TLS;
- OpenAPI docs по умолчанию отключены;
- настроены CSP, security headers, same-origin checks и безопасный reverse proxy;
- preflight проверяет Ubuntu, статический адрес/DNS, сертификаты и права private key;
- первый администратор создаётся отдельной fail-closed bootstrap-командой;
- CI содержит backend, frontend, integration, e2e и container jobs.

### 8.2. Блокеры и риски

- Backend и workers используют PostgreSQL bootstrap-owner, а MinIO — root credentials.
  Нужны отдельные migration/runtime/media/backup identities и проверенные grants.
- Автоматизированного backup/restore нет.
- Compose-сеть `parser-egress` сама по себе не ограничивает DNS/HTTPS назначения;
  нужен host firewall или network policy.
- Полный hardening (`read_only`, dropped capabilities, resource limits) применён не ко
  всем сервисам.
- Нет container vulnerability scan, SBOM, provenance и подписания образов.
- Нет встроенного централизованного monitoring/alerting и утверждённых capacity budgets.
- `main` не защищён ruleset/branch protection от force-push/delete и обхода CI.
- GitHub показывает два открытых Dependabot alert:
  - high, `react-router` 7.18.1, `GHSA-qwww-vcr4-c8h2`; затронут RSC/server-action path,
    который SPA не использует, поэтому CI имеет документированное точечное исключение,
    но alert нужно закрыть обновлением или формальным risk acceptance до релиза;
  - medium, `pytest` 8.4.2, `GHSA-6w46-j5rx-g56g`; это dev/test dependency, исправление
    доступно в 9.0.3, но текущий constraint `<9` требует планового обновления.

Основные файлы:

- `compose.yaml`
- `compose.production.yaml`
- `.env.example`
- `.env.production.example`
- `Dockerfile`
- `frontend/Dockerfile`
- `deploy/`
- `scripts/production_preflight.py`
- `scripts/production_smoke.py`
- `.github/workflows/quality.yml`
- `.github/dependabot.yml`
- `docs/DEPLOYMENT.md`
- `docs/SECURITY.md`
- `docs/THREAT_MODEL.md`

## 9. Резервное копирование

В документации backup указан как обязательное внешнее условие, однако в репозитории нет:

- команды согласованного `pg_dump`;
- копирования MinIO objects с общей точкой согласованности;
- шифрования, ротации и retention резервных копий;
- проверки целостности;
- restore-команды в чистое окружение;
- автоматизированного restore test;
- протокола успешной учебной аварии.

Это production blocker. Простого копирования Docker volumes недостаточно: PostgreSQL и
MinIO должны восстанавливаться согласованно, а процедура — регулярно проверяться.

Статус этапа 17: PostgreSQL-часть закрыта отдельной read-only backup identity, проверяемым
custom-format dump, checksum/manifest, безопасным restore только в `ackb_restore_*` и CI drill
для clean install, upgrade и сохранности критичных данных. MinIO objects, cross-store
consistency и выбранное оператором encrypted off-host storage остаются открытой частью этого
исходного finding.

## 10. Тесты и CI

Сильные стороны:

- 466 backend tests обнаружены pytest;
- frontend содержит 59 Vitest tests в 17 файлах;
- есть реальные integration tests PostgreSQL/MinIO;
- есть Playwright e2e, accessibility-friendly selectors и visual baseline;
- проверяются CSRF, RBAC, same-origin, IDOR, parser SSRF, миграции, deployment contract,
  media validation, idempotency, lease и retry;
- GitHub Actions для исходного commit прошёл все пять jobs.

Необходимые новые или изменённые тесты:

1. Полная матрица четырёх ролей и permissions для каждого endpoint.
2. Истечение, отзыв и продление временной роли `editor`.
3. Миграция всех существующих сочетаний ролей без повышения привилегий.
4. Вход без фиктивного выбора режима.
5. User-management API/UI и защита последнего администратора.
6. Все переходы нового lifecycle, включая запрещённые переходы.
7. Сохранение истории и авторства после archive/hide/final delete.
8. Предложение исправления преподавателем без прямого изменения карточки.
9. Audit API, фильтры, pagination, сокрытие секретов и неизменяемость.
10. Redis outage между commit и enqueue, reconciler/outbox, restart worker.
11. Отмена задания и повторная доставка без дублей.
12. Backup PostgreSQL + MinIO и автоматический restore drill.
13. Русские пользовательские ошибки без raw technical codes.
14. Проверка отсутствия запрещённых технических терминов в обычных разделах.
15. Keyboard-only, focus order, screen-reader labels, 320 px и все темы.
16. Новая кнопка темы и меню с touch target не менее 40×40 px.

Примечание по локальному окружению: проект поддерживает Node.js `>=22.12 <26`, CI
использует Node 22. На установленном Node 26.4 Vitest/jsdom не предоставляет
`localStorage`, поэтому все 59 тестов падают в общем teardown; это несовместимое
окружение, а не 59 независимых регрессий. Авторитетный повтор выполнен на Node 22.

## 11. Необходимые миграции

Точные имена ревизий следует назначать при выполнении этапов; ручное изменение live DB
не допускается.

### M1. Роли и grants

- добавить `editor` в допустимые значения;
- расширить `user_roles` сроком действия и состоянием grant либо создать отдельную
  таблицу role grants;
- хранить `granted_by`, `granted_at`, `expires_at`, `revoked_at`;
- добавить индексы активных grants;
- мигрировать существующих пользователей по явно утверждённой таблице соответствия;
- не превращать существующих преподавателей в редакторов автоматически без правила
  этапа 3.

### M2. Жизненный цикл и проверка

- расширить status до `draft`, `in_review`, `changes_requested`, `approved`,
  `published`, `hidden`, `archived`;
- добавить необходимые поля review/approval/visibility и их actor/time;
- перенести существующие `draft/published/archived` без потери snapshots;
- обновить check constraints и опубликованный search projection.

### M3. Предложения преподавателя и назначения редактора

Потребуется только если этапы 5–8 подтвердят отдельные сущности:

- correction proposals с автором и состоянием;
- назначения карточек редактору;
- решения review без смешивания с immutable revision snapshot.

### M4. Audit/query и очередь

- составные индексы audit для утверждённых фильтров;
- outbox/dispatch attempts либо поля reconciler для гарантированной доставки jobs;
- состояние отмены, если оно не укладывается безопасно в текущий enum.

### M5. Окончательное удаление

До реализации определить retention policy и FK-поведение для revisions, attribution,
media и audit. Миграция допустима только после готового backup/restore и теста, что
история не исчезает случайно.

## 12. Карта файлов по направлениям

| Направление | Ключевые файлы и каталоги |
|---|---|
| Модель прав | `auth/domain.py`, `auth/models.py`, `auth/repository.py`, `auth/service.py`, `api/dependencies.py`, `api/admin.py`, `frontend/src/api/contracts.ts`, `routing/guards.tsx` |
| Вход | `api/auth.py`, `frontend/src/pages/LoginPage.tsx`, `OledLoginDisplay.tsx` |
| Каталог/lifecycle | `catalog/domain.py`, `catalog/models.py`, `catalog/service.py`, `api/catalog.py`, `ComponentEditorPage.tsx`, `ComponentListPage.tsx` |
| История/авторство | `catalog/models.py`, `catalog/service.py`, `auth/models.py`, `SourceAttributionBlock.tsx` |
| Импорт | `api/imports.py`, `api/import_reviews.py`, `imports/`, `AdminImportPage.tsx`, `ImportReviewPage.tsx` |
| Очереди | `api/jobs.py`, `imports/queue.py`, `imports/tasks.py`, `media/queue.py`, `media/tasks.py`, `worker.py`, `AdminJobsPage.tsx` |
| Файлы/медиа | `api/media.py`, `media/`, `ComponentImagesEditor.tsx`, `MediaGallery.tsx` |
| Навигация/UI | `app/routes.tsx`, `AppHeader.tsx`, `AdminLayout.tsx`, `StudentLayout.tsx`, `styles/` |
| Тема | `ThemeToggle.tsx`, `theme/ThemeProvider.tsx`, `styles/global.css` |
| Ошибки | `middleware.py`, `api/client.ts`, `AsyncStates.tsx`, все admin/editor pages |
| Аудит | `auth/models.py`, `auth/repository.py`, сервисы mutations, новая admin page |
| Миграции | `migrations/versions/`, `tests/test_migrations.py`, integration tests |
| Production | `compose*.yaml`, `Dockerfile`, `deploy/`, `scripts/production_*`, `.github/workflows/quality.yml` |
| Backup/restore | новые operator scripts, `docs/DEPLOYMENT.md`, отдельные restore tests |
| Версия/release | `pyproject.toml`, `frontend/package*.json`, `compose*.yaml`, build args, release docs |

## 13. Приоритет блокеров

### P0 — до любого release candidate

1. Ввести целевую permission model и роль `editor`.
2. Убрать у `teacher` прямое редактирование, импорт, upload, публикацию и архивирование.
3. Добавить срок действия и административное управление ролью редактора.
4. Реализовать целевой lifecycle и серверные переходы.
5. Добавить безопасную миграцию существующих пользователей и карточек.
6. Реализовать и испытать backup/restore PostgreSQL + MinIO.
7. Устранить окно потери доставки DB-to-Redis.

### P1 — до ручной приёмки

1. Убрать фиктивный выбор роли на входе.
2. Добавить страницы пользователей, журнала, review/history и диагностики.
3. Полностью русифицировать обычный интерфейс и error states.
4. Скрыть инфраструктурные термины от ученика и преподавателя.
5. Переработать шапку, навигацию и theme control.
6. Добавить отмену/восстановление фоновых операций.
7. Закрыть или формально принять dependency alerts.

### P2 — production hardening/sign-off

1. Разделить инфраструктурные identities и права.
2. Добавить container scan, SBOM/provenance и полный service hardening.
3. Зафиксировать egress firewall, monitoring, alerting, retention и capacity.
4. Включить branch protection/ruleset.

## 14. Риски изменений

- Ошибка миграции ролей может незаметно повысить права существующего преподавателя.
- Замена role checks на permissions может оставить единичный endpoint со старой защитой;
  нужен автоматический route contract.
- Расширение lifecycle может нарушить видимость старой опубликованной snapshot.
- Изменение FK ради final delete может уничтожить историю или orphan media.
- Изменение queue semantics без идемпотентности может создать дубли карточек/файлов.
- Русификация raw codes не должна удалять request ID и машинный код из журналов.
- Backup считается готовым только после восстановления в чистой среде, а не после
  успешного создания архива.
- Изменение React Router ради alert может потребовать отдельной проверки guards и routing.
- Большие файлы `catalog/service.py`, `api/catalog.py`,
  `ComponentEditorPage.tsx` повышают риск связанных регрессий; изменения должны быть
  локальными и поэтапными.

## 15. Предлагаемый порядок

Сохраняется порядок исходного плана:

1. Этапы 2–6: permissions, миграция пользователей, вход, временные редакторы,
   серверная защита.
2. Этапы 7–8: lifecycle, история и авторство.
3. Этапы 9–15: загрузка компонентов, русификация, навигация, тема, безопасные файлы,
   ошибки и журнал.
4. Этапы 16–18: production security, backup/restore, надёжность очередей.
5. Этапы 19–23: доступность, полный test matrix, ручная приёмка, миграция и
   production-like deployment.
6. Этапы 24–27: документация, version bump, release candidate, финальный `v1.0.0`.

Самостоятельный переход между этапами не допускается. После каждого этапа нужны
миграции вместо ручного SQL, тесты, push в `release/1.0.0` и отдельное подтверждение
перехода дальше.

## 16. Проверки аудита

В ходе этапа выполнены:

- проверка ветки, commit и всех мест хранения версии;
- чтение API dependencies, auth/catalog/import/media/job сервисов и моделей;
- проверка всех 19 миграций и единственной Alembic head;
- поиск пользовательских английских и технических строк;
- проверка Compose, production overlay, CI и документации;
- чтение открытых Dependabot alerts;
- сбор 466 backend tests без исполнения;
- запуск 59 frontend tests на поддерживаемом Node 22;
- проверка здоровья работающего локального Compose-стенда.

На этом этапе функциональный код, схема базы и пользовательские данные не изменялись.
