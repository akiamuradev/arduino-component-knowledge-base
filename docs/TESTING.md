# Автоматизированное тестирование

Этап 19 разделяет быстрые проверки и тесты реальной инфраструктуры. Обычный `pytest`
выполняет unit, contract и API-тесты без внешней сети. Исторические HTML fixtures сохраняются
для regression/audit. Repository contract дополнительно использует Seeed Markdown/MDX и KiCad
S-expression fixtures и подтверждает full commit, typed status/warnings, field provenance,
license snapshot, idempotency identity и неизменный `draft`.

## Локальные проверки

Backend:

```bash
ruff check .
ruff format --check src scripts tests migrations
mypy --strict src scripts tests migrations
pytest
python -m build
python scripts/backend_smoke.py
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run smoke
npx playwright install chromium
npm run test:e2e
```

Playwright запускает собранный frontend через Vite preview. Тест перехватывает HTTP API на
границе браузера, проверяет redirect на login, отправку credentials и переход administrator в
защищённый dashboard. Дополнительный student flow проверяет catalog, смену темы, detail,
безопасную source attribution, подсказку и скрытое решение. Реальная backend-авторизация отдельно
проверяется integration-контуром. Тестовые ответы отсутствуют в production bundle.

Vitest проверяет menu-button оформления, сохранение трёх режимов, реакцию системного режима,
активную отметку и клавиши Arrow/Home/End/Enter/Escape/Tab. Playwright подтверждает область
нажатия 44×44 px и отсутствие переполнения открытого меню на ширине 320 px.

Vitest дополнительно проверяет editor/administrator repository import: bounded discovery,
entry selection, preview с license/provenance, создание draft job и переход к готовому черновику.
Страница «Загрузка компонентов» проверяет русские состояния, безопасный результат,
отсутствие технических подробностей, ownership actions editor и administrator-only диагностику.
Тест подтверждает отсутствие вызова publish. Страница `/sources` проверяется на разделение active
и disabled источников и безопасные внешние ссылки. Stage 12 проверяет отдельные панели module
connection/internal components/KiCad symbol, confidence/evidence, optimistic review actions и
administrator-only маршрут `/admin/import-reviews`.

Журнал действий проверяется на обеих границах: backend contract требует ровно `audit.view`,
не допускает mutation route, применяет точные user/action/date filters, ограничивает страницу
и не включает `details_safe_json`/request ID. Allowlist durable details отвергает поля
`password`, `token`, `secret`, вложенные и неограниченные значения. Vitest подтверждает русский
read-only экран, безопасные actor/action/object labels и формирование всех трёх фильтров.

Контракт `ui-copy.contract.test.ts` проверяет утверждённые русские названия продукта и запрещает
возвращение ключевых демонстрационных или англоязычных строк в пользовательские страницы,
компоненты, макеты и route guards. Он также блокирует пользовательские упоминания внутренних
хранилищ, очередей и `request_failed`. Внутренние API-поля и enum в этот контракт не входят.

Контракт ошибок проверяется на обеих границах. Backend-тесты подтверждают единый
`error.code/message/retryable/request_id`, сохранение `Retry-After`, сокрытие validation input и
текста исключения при наличии его класса в структурированном журнале. Frontend-тесты проверяют
разбор envelope, безопасную совместимость со старым `detail.code`, сетевую ошибку с возможностью
повтора и отсутствие технических кодов в диагностике обработки.

Четыре утверждённых visual artifacts для light/dark и desktop/mobile воспроизводятся только при
`ACKB_UPDATE_SCREENSHOTS=1`. Обычный CI не перезаписывает файлы и отображает visual-update test
как явный skip. После перезагрузки visual test ждёт целевой заголовок страницы, чтобы снимок
не зафиксировал промежуточный экран проверки сессии.

## PostgreSQL и MinIO integration

Контур намеренно не выбирает произвольный локальный `.env`. Нужны disposable PostgreSQL и
MinIO, затем схема применяется только Alembic:

```bash
export ACKB_RUN_INTEGRATION=1
export ACKB_DATABASE_URL='postgresql+asyncpg://ackb:test-password@127.0.0.1:5432/ackb'
export ACKB_AUTH_THROTTLE_PEPPER='integration-only-placeholder-value'
export ACKB_REDIS_URL='redis://127.0.0.1:6379/15'
export ACKB_MINIO_ENDPOINT='127.0.0.1:9000'
export ACKB_MINIO_ACCESS_KEY='test-access'
export ACKB_MINIO_SECRET_KEY='test-secret-placeholder'
export ACKB_MINIO_SECURE=false
alembic upgrade head
pytest -m integration --strict-markers
```

Использовать production database или bucket запрещено: тесты создают и удаляют пользователей и
объекты. При обычном `pytest` integration-тесты отображаются как явные skip. В CI отдельный job
поднимает PostgreSQL и pinned MinIO, применяет `alembic upgrade head` и запускает marker с
`ACKB_RUN_INTEGRATION=1`, поэтому отсутствие сервисов или миграций приводит к ошибке job.

Проверяемые критические сценарии:

- фактическое наличие Alembic revision и ключевых PostgreSQL tables;
- Argon2id login всех четырёх ролей, серверные permissions, запрет role spoofing, opaque cookies,
  CSRF, administrator mutation, backend RBAC и logout;
- точный permission contract каждого фактического API method/path, включая lazy included routers,
  прямые отрицательные запросы student/teacher/editor и обязательный CSRF для administrator;
- одинаковый `404` для отсутствующего и чужого media/import UUID, в том числе retry чужого
  import job, без изменения job и без постановки в очередь;
- terminal cancellation import job: worker не начинает отменённую операцию и не заменяет
  `cancelled` на `failed`;
- transactional import/media dispatch, безопасный Redis failure, bounded delivery attempts,
  восстановление потерянного queued message и redelivery после перезапуска worker с истёкшей lease;
- early rejection traversal/control-character paths и неподдерживаемых repository extensions;
- PostgreSQL-serialized active/rate quotas для import и media reservation, включая
  идемпотентный replay без повторного расходования лимита;
- safe audit для accepted/rejected upload/import без raw path, содержимого, presigned URL или
  внутреннего exception;
- read-only audit journal, обязательный `audit.view`, safe projection, фильтры
  user/action/date и индексы `actor+occurred_at`/`action+occurred_at`;
- полный PostgreSQL lifecycle временного editor: создание с безопасной базовой ролью, срок,
  досрочный отзыв, повторное назначение, session revocation, disable, история grants и audit;
- PostgreSQL unique constraint для login;
- создание private MinIO buckets без public policy, upload/stat/download/presign/delete;
- исторический parser contract и новые Seeed/KiCad repository fixtures без внешней сети;
- запрет MDX/external-command execution, library allowlist и malformed document isolation;
- repository idempotency, source deactivation и publish rejection без license snapshot;
- полный lifecycle карточки `draft -> in_review -> changes_requested -> in_review -> approved
  -> published -> hidden -> published -> archived -> restored`, запрет недопустимых переходов,
  editor publish/review и физического delete, а также сохранение старого published snapshot
  после редактирования;
- immutable card history с actor/time, previous/new status и safe summary, совпадение metadata
  с audit event, owner-only доступ editor, полный scope administrator, сохранение истории после
  disable пользователя и отсутствие snapshot/teacher-only данных в history response;
- evidence-first review revision locking, immutable snapshots and append-only action audit;
- frontend unit tests и Chromium Playwright flow.

Не покрываются этим этапом: производительные нагрузки, реальные внешние сайты, полный browser
flow через Docker Compose reverse proxy и FFmpeg на Windows. Эти проверки относятся к этапам
стабилизации и приёмки, а не расширяют функциональный scope.

Этап 20 добавляет `scripts/production_contract_smoke.sh`: Linux CI проверяет объединённый
production Compose и выполняет `nginx -t` с одноразовым тестовым сертификатом. Реальный
корпоративный hostname/CA проверяются после развёртывания командой
`python scripts/production_smoke.py`; insecure TLS fallback отсутствует.

Этап 17 добавляет `scripts/database_restore_smoke.sh`. В полностью disposable production-like
Compose project он применяет всю Alembic chain на чистую базу, отдельно обновляет предыдущий
head `20260729_25` до текущего, создаёт PostgreSQL dump и восстанавливает его в
`ackb_restore_drill`. Manifest доказывает сохранность тестовых пользователя, роли, карточки,
revision history и audit event. Скрипт удаляет тестовые базы, volumes и временные credentials.
