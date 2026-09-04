# Тестирование

Тесты разделены на быстрый локальный контур, интеграцию с одноразовой инфраструктурой,
браузерные сценарии и production-like проверки. Fixtures не обращаются к внешней сети и не
содержат секретов.

## Быстрый контур

Backend:

```bash
uv lock --check
uv sync --frozen --extra dev
uv run pip-audit --strict --requirement requirements.lock --require-hashes
uv run bandit -r src/arduino_component_kb -q -ll
uv run ruff check .
uv run ruff format --check src scripts tests migrations
uv run mypy --strict src scripts tests migrations
uv run pytest
uv run python -m build
uv run python scripts/docs_contract.py
uv run python scripts/release_contract.py
uv run python scripts/backend_smoke.py
```

Frontend:

```bash
cd frontend
npm ci
npm run audit
npm run lint
npm run typecheck
npm test
npm run build
npm run smoke
npx playwright install chromium
npm run test:e2e
```

Vitest проверяет компоненты, маршруты, русский интерфейс, permission-based navigation, обработку
ошибок, редактор, импорт, медиа и audit read model. Playwright запускает production frontend
через Vite preview и проверяет вход, каталог, карточки, роли, multiple-image lifecycle,
repository import, клавиатурную навигацию, темы и ширину 320 px. `@axe-core/playwright`
блокирует нарушения WCAG в основных пользовательских потоках.

Visual screenshots обновляются только при явном opt-in:

```bash
cd frontend
ACKB_UPDATE_SCREENSHOTS=1 npm run test:e2e
```

Обычный CI не изменяет эталонные изображения и отмечает visual-update сценарий как skip.

## Интеграция PostgreSQL и MinIO

Интеграционные тесты разрешены только на одноразовых сервисах: они создают и удаляют данные.
Схема всегда применяется через Alembic; runtime `create_all` не используется.

```bash
export ACKB_RUN_INTEGRATION=1
export ACKB_DATABASE_URL='postgresql+asyncpg://ackb:test-password@127.0.0.1:5432/ackb'
export ACKB_AUTH_THROTTLE_PEPPER='integration-only-placeholder-value'
export ACKB_REDIS_URL='redis://127.0.0.1:6379/15'
export ACKB_MINIO_ENDPOINT='127.0.0.1:9000'
export ACKB_MINIO_ACCESS_KEY='test-access'
export ACKB_MINIO_SECRET_KEY='test-secret-placeholder'
export ACKB_MINIO_SECURE=false
uv run alembic upgrade head
uv run pytest -m integration --strict-markers
```

Контур проверяет:

- Argon2id login, opaque sessions, CSRF и backend RBAC всех ролей;
- PostgreSQL constraints, migrations, lifecycle карточек и immutable revisions;
- ownership и одинаковый `404` для чужих и отсутствующих объектов;
- transactional job dispatch, Redis failure/recovery, retry, cancel и lease takeover;
- quotas, idempotency и append-only audit;
- private MinIO upload/download, media validation и retention;
- repository parser contracts, provenance, license snapshots и review workspace;
- обновление с опубликованной схемы `v0.21.0` и восстановление pre-upgrade dump.

При обычном `pytest` integration tests ожидаемо пропускаются.

## Production-like проверки

```bash
bash scripts/production_contract_smoke.sh
bash scripts/production_identity_smoke.sh
bash scripts/database_restore_smoke.sh
bash scripts/clean_stack_smoke.sh
```

`clean_stack_smoke.sh` создаёт отдельный Compose project, применяет все миграции на чистых
volumes, проверяет пустые business tables и HTTP readiness, затем удаляет одноразовые ресурсы.
`database_restore_smoke.sh` проверяет backup, upgrade, downgrade и restore. Эти скрипты нельзя
направлять на production database или bucket.

## CI gate

Workflow `quality` содержит обязательные jobs:

| Job | Область |
|---|---|
| `backend` | lint, types, unit/API tests, audit, package и docs contracts |
| `frontend` | clean install, audit, lint, types, Vitest и production build |
| `integration` | PostgreSQL, MinIO, Alembic и integration marker |
| `e2e` | Chromium Playwright и accessibility |
| `containers` | Compose, images, clean install, identity и restore smokes |
| `release-quality-gate` | требует `success` каждого предыдущего job |

Skipped, cancelled или failed обязательный job блокирует релиз.

## Границы автоматизации

CI не заменяет нагрузочные и длительные тесты, реальный внешний импорт, Firefox/WebKit,
физическое восстановление VM, корпоративные DNS/CA/firewall и согласованный PostgreSQL + MinIO
backup. Эти проверки выполняются на приёмочном стенде по [QA checklist](QA_CHECKLIST.md).
