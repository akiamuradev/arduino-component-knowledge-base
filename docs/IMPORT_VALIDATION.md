# Проверка repository imports на Linux VM

Документ относится к ограниченной проверке Seeed Studio Wiki и Official KiCad Symbols. Он не
разрешает массовый импорт и публикацию тестовых карточек. Импорт всегда заканчивается черновиком.

## Требования

- Linux VM с 4 vCPU, 6 GiB RAM и минимум 20 GiB свободного места;
- Docker Engine и Compose plugin;
- `curl`, `openssl`, Git и Python 3;
- исходящий HTTPS к `api.github.com` и `gitlab.com`;
- отсутствие опубликованных host ports у PostgreSQL, Redis и MinIO.

MinIO входит в validation profile только потому, что текущий backend lifecycle использует общий
media storage. Repository parser не сохраняет в MinIO исходные документы.

## Подготовка и запуск

Из корня репозитория создайте локальный `.env`, не выводя сгенерированные значения в терминал:

```fish
bash scripts/linux_bootstrap.sh
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml config --quiet
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml up --build -d \
  postgres redis minio migrate media-init backend parser-worker
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml ps
```

Если репозиторий находится на файловой системе без Unix mode bits, запуск через `bash` не требует
`chmod +x`. Файл `.env` запрещено добавлять в Git.

Проверка миграций и health:

```fish
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml logs migrate
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml exec backend \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready').read()"
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml exec backend \
  alembic current
```

## Фиксация revision

Клиент передаёт tag, branch или полный SHA только для зарегистрированного `source_key`. Worker
разрешает значение через официальный provider API и сохраняет полный 40-символьный commit SHA.
Файл затем читается через API этого же provider. Clone, submodules, hooks, package scripts, MDX/JS и
documentation build не запускаются; архивы не распаковываются. Лимиты задаются переменными:

- `ACKB_REPOSITORY_CONNECT_TIMEOUT_SECONDS`;
- `ACKB_REPOSITORY_READ_TIMEOUT_SECONDS`;
- `ACKB_REPOSITORY_TOTAL_TIMEOUT_SECONDS`;
- `ACKB_REPOSITORY_MAX_RESPONSE_BYTES`;
- `ACKB_REPOSITORY_MAX_FILE_BYTES`;
- `ACKB_KICAD_LIBRARY_ALLOWLIST`.

Обнаружение metadata возвращает не более 100 файлов. Для Seeed сканируется только
`sites/en/docs`, для KiCad 9.x — только библиотеки `.kicad_sym` в корне. Лимит ответа с metadata
провайдера по умолчанию равен 8 MiB, а лимит одного импортируемого исходного файла остаётся 2 MiB.

## Проверка путей и образцов

Administrator может найти допустимые пути без клонирования репозитория:

```http
GET /api/v1/import-jobs/repository/discovery?source_key=seeed_wiki&revision=docusaurus-version&q=Grove%20Button&limit=5
GET /api/v1/import-jobs/repository/discovery?source_key=kicad_symbols&revision=9.0.9.1&q=Sensor%20Temperature&limit=5
```

Ответ содержит полный resolved SHA, число просмотренных записей и не более запрошенного количества
путей. Endpoint не принимает repository URL от клиента и повторно проверяет роль administrator.

После выбора файла UI запрашивает bounded entry discovery и preview без записи в PostgreSQL:

```http
GET /api/v1/import-jobs/repository/entries?source_key=kicad_symbols&revision=9.0.9.1&file_path=Sensor_Temperature.kicad_sym&limit=50
POST /api/v1/import-jobs/repository/preview
```

Preview возвращает нормализованные поля, warnings, provenance, resolved SHA и license snapshot.
Только после ручной проверки administrator нажимает «Создать черновик»; отдельного действия
«импортировать и опубликовать» нет.

Перед полными jobs запустите фиксированный smoke-набор: ровно пять Seeed документов и десять
символов из `Sensor_Temperature.kicad_sym` стабильного тега KiCad 9.0.9.1. Команда только скачивает
ограниченные исходники, разбирает их в памяти и печатает безопасную сводку; БД и MinIO она не меняет:

```fish
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml run --rm backend \
  ackb-validate-repository-samples
```

Успех — `ok: true`, `failure_count: 0`, пять элементов `seeed`, десять элементов `kicad` и полные
SHA обеих ревизий. `parsed_with_warnings` допустим для неизвестных необязательных разделов Seeed;
`invalid_metadata`, `source_drift` и `unsupported_document` завершают команду ненулевым кодом.

Затем создайте те же 15 образцов полным путём HTTP → PostgreSQL → Redis/Dramatiq → parser worker →
draft. Пароль читается скрытым prompt и не выводится в команду или отчёт:

```fish
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml exec backend \
  ackb-validate-repository-jobs --login admin
```

Успех — `ok: true`, `job_count: 15`, `idempotency_replay: true`; у каждого job должны быть
`status=succeeded`, допустимый parse status, полный SHA и `draft_component_id`. Команда не вызывает
publish. Сохраните выведенные job и draft UUID для проверки после перезапусков и контролируемой
очистки.

## Dry-run

Dry-run читает только уже полученный локальный файл и требует полный SHA:

```fish
set revision 0123456789abcdef0123456789abcdef01234567
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml run --rm backend \
  ackb-import-dry-run --source seeed --repository-root /fixtures --revision $revision \
  --file path/to/document.md
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml run --rm backend \
  ackb-import-dry-run --source kicad --repository-root /fixtures --revision $revision \
  --file Sensor_Temperature.kicad_sym --entry LM35-D
```

`/fixtures` необходимо смонтировать явно как read-only каталог VM. Не используйте выдуманный path:
его сначала подтверждают по официальному репозиторию.

## Полный job

После входа administrator и получения CSRF token UI или API отправляет:

```http
POST /api/v1/import-jobs/repository
Idempotency-Key: <new-random-key>
Content-Type: application/json

{"source_key":"seeed_wiki","revision":"<tag-or-sha>","file_path":"<verified-path>"}
```

Для KiCad добавляются `source_key=kicad_symbols` и обязательный `entry_name`. Backend повторно
проверяет роль administrator. Один и тот же Idempotency-Key с другим payload возвращает `409`.
Один и тот же repository/commit/file/entry переиспользует существующий draft.

Просмотр job:

```http
GET /api/v1/import-jobs/<job-id>
```

Ответ содержит attempts, heartbeat, retry state, полный resolved SHA, parse status, warnings и
ограниченные metrics. Traceback и содержимое документа в API и logs не возвращаются.

## Failure tests

Проверяются отдельными небольшими jobs или автоматическими тестами:

| Сценарий | Ожидаемый typed code/результат |
|---|---|
| неизвестный source/repository | `source_disabled` / `repository_not_allowlisted` |
| неверный ref или path | `repository_entry_not_found` |
| private DNS answer | `repository_dns_address_invalid` |
| превышение response/file limit | `repository_response_too_large` / `repository_file_too_large` |
| повреждённый Markdown/S-expression | `repository_invalid_metadata` или parser status |
| partial parse | succeeded draft + `parsed_with_warnings` |
| provider 429/5xx/timeout или GitHub 403 с исчерпанным rate limit | bounded retry с backoff |
| denied source | `source_disabled`, job не создаётся |
| publish без license snapshot | typed `source_license_missing` |
| повторная доставка | тот же job/draft, без второго component |

Для Redis, worker и PostgreSQL restart используйте только Compose restart; volumes не удаляйте:

```fish
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml restart parser-worker
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml restart redis
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml restart postgres
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml ps
```

После каждого restart дождитесь healthy и повторно запросите job. Не используйте `down -v`.

## Logs и PostgreSQL

```fish
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml logs \
  --since 15m backend parser-worker
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml exec postgres \
  psql -U ackb -d ackb -c "SELECT id,status,parse_status,attempts,source_revision,heartbeat_at,draft_component_id,error_code FROM import_jobs ORDER BY created_at DESC LIMIT 20;"
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml exec postgres \
  psql -U ackb -d ackb -c "SELECT c.status,cs.source_revision,cs.license_snapshot_spdx,jsonb_object_length(cs.provenance_json) AS provenance_fields FROM component_sources cs JOIN components c ON c.id=cs.component_id ORDER BY cs.imported_at DESC LIMIT 20;"
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml exec postgres \
  psql -U ackb -d ackb -c "SELECT c.id FROM components c JOIN component_sources cs ON cs.component_id=c.id LEFT JOIN component_revisions r ON r.component_id=c.id AND r.status='published' WHERE cs.source_revision IS NOT NULL AND r.id IS NOT NULL;"
```

Последний запрос для тестовых drafts должен вернуть ноль строк. Повторный импорт проверяется по
числу уникальных `component_sources` для source/revision/file/entry.

## Тесты и восстановление

```fish
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
docker compose --env-file .env -f compose.yaml -f compose.vm-validation.yaml restart parser-worker
```

Failed job не переводится вручную в succeeded. После устранения retryable причины его повторно
доставляет очередь в пределах `max_attempts`; terminal failure запускают новым Idempotency-Key.
Очистка допустима только для заранее записанных UUID тестовых drafts и выполняется оператором в
транзакции после проверки зависимостей. Автоматической очистки и удаления volumes нет.

## Известные ограничения

- validation profile не заменяет проверку реальной Linux VM;
- provider rate limits могут потребовать паузу, но credentials не сохраняются и токены не нужны;
- массовый discovery/import намеренно отсутствует;
- конкретные Seeed paths и KiCad symbol names проверяются на выбранном commit перед job;
- тестовые карточки остаются draft и не должны публиковаться.
