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

Четыре утверждённых visual artifacts для light/dark и desktop/mobile воспроизводятся только при
`ACKB_UPDATE_SCREENSHOTS=1`. Обычный CI не перезаписывает файлы и отображает visual-update test
как явный skip.

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
- Argon2id login, opaque cookies, CSRF, administrator mutation, backend RBAC и logout;
- PostgreSQL unique constraint для login;
- создание private MinIO buckets без public policy, upload/stat/download/presign/delete;
- исторический parser contract и новые Seeed/KiCad repository fixtures без внешней сети;
- запрет MDX/external-command execution, library allowlist и malformed document isolation;
- repository idempotency, source deactivation и publish rejection без license snapshot;
- frontend unit tests и Chromium Playwright flow.

Не покрываются этим этапом: производительные нагрузки, реальные внешние сайты, полный browser
flow через Docker Compose reverse proxy и FFmpeg на Windows. Эти проверки относятся к этапам
стабилизации и приёмки, а не расширяют функциональный scope.

Этап 20 добавляет `scripts/production_contract_smoke.sh`: Linux CI проверяет объединённый
production Compose и выполняет `nginx -t` с одноразовым тестовым сертификатом. Реальный
корпоративный hostname/CA проверяются после развёртывания командой
`python scripts/production_smoke.py`; insecure TLS fallback отсутствует.
