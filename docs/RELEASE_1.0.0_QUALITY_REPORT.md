# Отчёт о полном контроле качества ACKB 1.0.0

Дата проверки: 2026-07-29. Ветка: `release/1.0.0`.

Этот отчёт фиксирует матрицу этапа 20 до изменения номера версии. Проверяется текущая
предрелизная версия `0.21.0`; переход на `1.0.0`, финальный commit SHA и release artifacts
выполняются только на последующих этапах плана.

## Обязательный автоматический контур

| Область | Проверка | Результат |
|---|---|---|
| Форматирование | `ruff format --check src scripts tests migrations` | пройдено |
| Статический анализ | `ruff check`, Bandit, pip-audit, npm audit, ESLint | пройдено |
| Типизация | strict mypy, TypeScript application и E2E configs | пройдено |
| Модульные и контрактные тесты | полный pytest без integration marker, полный Vitest | пройдено |
| Интеграция и API | PostgreSQL 17 + MinIO, Alembic head, `pytest -m integration` | пройдено |
| Роли и вход | permission route contract, отрицательные запросы ролей, Argon2id login/session/CSRF | пройдено |
| Карточки | lifecycle, revision conflict, history, publish snapshot, media gallery | пройдено |
| Загрузка компонентов | repository fixtures, preview, provenance/license, idempotency, quotas | пройдено |
| Фоновая обработка | transactional dispatch, retry/cancel, lease, Redis failure/recovery | пройдено |
| Пользовательский интерфейс | Vitest и Chromium Playwright, axe/WCAG, ширина 320 px, обе темы | пройдено |
| Производственная сборка | Python wheel/sdist, Vite bundle, три Docker image, nginx/Compose contracts | пройдено |
| Чистая база | изолированный полный Compose, все миграции, пустые business tables, HTTP smoke | пройдено |
| Обновление и восстановление | previous Alembic head → current head, PostgreSQL dump/restore | пройдено |

GitHub workflow `quality` разделяет проверки на `backend`, `frontend`, `integration`, `e2e`
и `containers`. Job `release-quality-gate` выполняется даже после ошибки зависимости и становится
зелёным только тогда, когда все пять обязательных jobs завершились со статусом `success`.
Пропущенный, отменённый или упавший job не считается успешным.

## Результат локального прогона

Финальный прогон этапа выполнен 2026-07-29:

- backend: 649 обычных тестов пройдено; 15 integration tests ожидаемо пропущены без opt-in;
- integration: отдельно пройдено 15 из 15 тестов на одноразовых PostgreSQL 17 и MinIO;
- frontend: 80 из 80 Vitest tests пройдено;
- browser: 7 из 7 обязательных Chromium E2E пройдено, visual-update test ожидаемо пропущен;
- strict mypy, TypeScript typecheck, Ruff format/lint, ESLint и Bandit прошли;
- pip-audit не обнаружил известных уязвимостей;
- wheel, sdist, Vite bundle и Docker images собраны;
- clean-stack, production identity и database upgrade/restore smokes прошли.

Во время прогона устранено использование deprecated `SQLAlchemy Row.tuple()` в repositories.
После замены повторные unit и integration tests завершились без deprecation warnings.

## Воспроизводимый запуск на чистой базе

`scripts/clean_stack_smoke.sh` создаёт отдельный Compose project и одноразовые credentials,
запускает PostgreSQL, Redis, MinIO, миграции, backend, frontend, workers, reconciler и reverse
proxy. Host port выбирается Docker автоматически, поэтому тест не конфликтует с локальным ACKB.

Скрипт проверяет:

- единственную Alembic head revision;
- ноль записей в `users`, `components` и `import_jobs`;
- healthy всех постоянных сервисов;
- ответы `/health`, `/ready` и production frontend;
- удаление контейнеров, сетей, volumes и временного environment file после завершения.

Обычный запуск сам воспроизводимо собирает образы:

```bash
bash scripts/clean_stack_smoke.sh
```

В CI образы сначала собираются отдельным обязательным шагом, поэтому повторная сборка отключается
только для этого запуска:

```bash
ACKB_CLEAN_STACK_SKIP_BUILD=true bash scripts/clean_stack_smoke.sh
```

## Ручные проверки

Автоматический результат не заменяет следующие проверки перед выпуском:

1. Визуально просмотреть утверждённые desktop/mobile screenshots без обрезки текста и наложений.
2. Выполнить сценарии ученика, преподавателя, редактора и администратора из этапа 21.
3. Проверить режим «Как на устройстве» на реальном браузере и переключение системной темы.
4. Загрузить небольшое реальное изображение и открыть его варианты через установленный стенд.
5. На тестовой VM проверить TLS hostname/CA, HTTP→HTTPS, внутренний DNS и разрешённый client VLAN.
6. С внешнего VLAN подтвердить firewall deny; убедиться, что 5432, 6379, 9000 и 9001 не опубликованы.
7. Выполнить ограниченный импорт из зафиксированных ревизий Seeed/KiCad при доступной внешней сети.
8. Проверить backup/restore вместе с фактическим MinIO backup по эксплуатационной инструкции.
9. Подтвердить метрики, alerts, свободное место и время выполнения на целевом оборудовании.

Подробные пошаговые сценарии по ролям намеренно относятся к этапу 21 и здесь не дублируются.

## Известные ограничения

- Browser E2E выполняется в Chromium; Firefox, WebKit и мобильные устройства проверяются вручную.
- Внешние репозитории не используются в детерминированном CI: parser contracts работают на
  закреплённых fixtures, а реальный сетевой импорт остаётся ручной проверкой.
- Нагрузочные, длительные soak- и chaos-тесты не входят в scope 1.0.0.
- Visual test не перезаписывает утверждённые screenshots без `ACKB_UPDATE_SCREENSHOTS=1`.
- npm audit содержит формально принятую advisory React Router для RSC/server actions: ACKB является
  client-only Vite SPA и не включает затронутый execution path. Любое появление другого high или
  critical finding блокирует CI.
- Корпоративные DNS, CA, firewall, capacity и физическое восстановление VM зависят от целевой
  инфраструктуры и не могут быть доказаны в GitHub-hosted runner.

Эти ограничения не скрывают упавшие проверки и не отключают обязательные jobs. Они определяют
границу автоматической проверки и входные данные для ручной приёмки.
