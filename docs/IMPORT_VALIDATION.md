# Проверка импорта на Linux VM

Инструкция проверяет ограниченный импорт из Seeed Studio Wiki и Official KiCad Symbols. Она не
разрешает массовую загрузку или публикацию: результат всегда остаётся черновиком.

## Требования

- Linux VM: 4 vCPU, 6 GiB RAM, 20 GiB свободного места;
- Docker Engine и Compose plugin, `curl`, `openssl`, Git и Python 3;
- исходящий HTTPS к `api.github.com` и `gitlab.com`;
- PostgreSQL, Redis и MinIO не публикуют host ports.

## Запуск стенда

Команды подходят для fish, потому что shell-скрипт явно запускается через `bash`:

```fish
bash scripts/linux_bootstrap.sh
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml config --quiet
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml up --build -d \
  postgres redis minio migrate media-init backend parser-worker
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml ps
```

`.env` не добавляют в Git и не выводят в терминал. Проверьте migration и readiness:

```fish
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml logs migrate
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml exec backend \
  alembic current
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml exec backend \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready').read()"
```

## Безопасная граница

Клиент передаёт только зарегистрированный `source_key`, revision и путь. Worker разрешает tag,
branch или SHA через официальный provider API и сохраняет полный commit SHA. Repository URL не
принимается от клиента. Clone, archives, submodules, hooks, package scripts, MDX/JS и docs build
не запускаются.

Основные ограничения задают:

- `ACKB_REPOSITORY_*_TIMEOUT_SECONDS`;
- `ACKB_REPOSITORY_MAX_RESPONSE_BYTES` и `ACKB_REPOSITORY_MAX_FILE_BYTES`;
- `ACKB_KICAD_LIBRARY_ALLOWLIST`.

Discovery возвращает не более 100 файлов. Seeed ограничен `sites/en/docs`, KiCad — allowlisted
`.kicad_sym` в корне. Каждый redirect, DNS answer, размер и путь проверяется повторно.

## Preview и фиксированный smoke

Administrator сначала выполняет discovery и preview без записи в PostgreSQL:

```http
GET /api/v1/import-jobs/repository/discovery?source_key=seeed_wiki&revision=docusaurus-version&q=Grove%20Button&limit=5
GET /api/v1/import-jobs/repository/entries?source_key=kicad_symbols&revision=9.0.9.1&file_path=Sensor_Temperature.kicad_sym&limit=50
POST /api/v1/import-jobs/repository/preview
```

Preview должен показать resolved SHA, поля, warnings, provenance и license snapshot. После этого
запустите фиксированный набор из пяти Seeed документов и десяти KiCad symbols. Он разбирается в
памяти и не меняет базу:

```fish
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml run --rm backend \
  ackb-validate-repository-samples
```

Ожидается `ok: true`, `failure_count: 0` и полные SHA. `parsed_with_warnings` допустим для
необязательных незнакомых секций; `invalid_metadata`, `source_drift` и
`unsupported_document` считаются ошибкой.

Полный HTTP → PostgreSQL → Dramatiq → parser worker → draft сценарий:

```fish
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml exec backend \
  ackb-validate-repository-jobs --login admin
```

Ожидается `ok: true`, 15 успешных jobs, `idempotency_replay: true`, полный SHA и
`draft_component_id` у каждого результата. Команда не публикует карточки.

## Локальный dry-run

Dry-run принимает уже полученный read-only snapshot и полный SHA:

```fish
set revision 0123456789abcdef0123456789abcdef01234567
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml run --rm backend \
  ackb-import-dry-run --source seeed --repository-root /fixtures --revision $revision \
  --file path/to/document.md
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml run --rm backend \
  ackb-import-dry-run --source kicad --repository-root /fixtures --revision $revision \
  --file Sensor_Temperature.kicad_sym --entry LM35-D
```

`/fixtures` монтируют явно как read-only; путь сначала подтверждают в официальном repository.

## Проверка отказов

| Сценарий | Ожидаемый результат |
|---|---|
| Неизвестный или запрещённый source | `source_disabled` / `repository_not_allowlisted` до fetch |
| Неверный ref/path | `repository_entry_not_found` |
| Non-public DNS | `repository_dns_address_invalid` |
| Превышение лимита | `repository_response_too_large` / `repository_file_too_large` |
| Повреждённый документ | `repository_invalid_metadata` или typed parser status |
| Частичный разбор | Успешный draft с `parsed_with_warnings` |
| Provider 429/5xx/timeout | Ограниченный retry с backoff |
| Publication без license | `source_license_missing` |
| Повторная доставка | Тот же job/draft без второго component |

После контролируемого restart дождитесь healthy и повторно проверьте job. Volumes не удаляйте:

```fish
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml restart parser-worker
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml restart redis
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml ps
```

## Результат и очистка

Зафиксируйте source key, полный revision, job/draft UUID, parse status, warnings и итог. В отчёт не
копируют source body, credentials, presigned URL или traceback. Убедитесь, что тестовые drafts не
имеют published revision.

Terminal failure не переводят вручную в `succeeded`: retryable job повторяет очередь, остальные
запускают новым idempotency key после устранения причины. Удалять разрешено только заранее
записанные UUID тестовых draft после проверки зависимостей. `down -v` для общего стенда запрещён.

Validation profile не заменяет проверку целевой VM, rate limits provider и firewall. Массовый
discovery/import намеренно отсутствует.
