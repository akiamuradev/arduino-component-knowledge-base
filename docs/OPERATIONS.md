# Эксплуатация ACKB 1.0.0

Этот документ предназначен для системного администратора ACKB. Он описывает установку,
обновление, обслуживание и восстановление одной production VM на Ubuntu Server 24.04 LTS.
Сетевой baseline, TLS, firewall и устройство production Compose подробно описаны в
[runbook развёртывания](DEPLOYMENT.md). Здесь собрана последовательность ежедневных и аварийных
операций.

Все действия выполняются из корня проверенного checkout. Перед изменением состояния запишите
полный commit SHA, время UTC, оператора и номер заявки. Не записывайте в заявку пароли, cookies,
токены, содержимое `.env.production`, private keys или пользовательские данные.

## Общие обозначения

Примеры ниже рассчитаны на `fish`. В начале каждой операторской сессии задайте общую Compose
команду:

```fish
set project arduino-component-kb
set env_file .env.production
set compose docker compose --project-name $project --env-file $env_file \
  -f compose.yaml -f compose.production.yaml
```

Имя project определяет имена Docker volumes. Не меняйте его между запуском, backup и restore.
Перед командой с остановкой или восстановлением проверьте `pwd`, `git status`, `$project` и
`$env_file`.

## 1. Установка на чистом сервере

1. Подготовьте Ubuntu Server 24.04 LTS со статическим IP, внутренним DNS, синхронизацией времени
   и console-access. Сначала согласуйте firewall и установку внутреннего CA по
   [production runbook](DEPLOYMENT.md#1-ubuntu-server-и-static-ip).
2. Установите поддерживаемые организацией Docker Engine и Compose plugin, затем Git, `curl`,
   `openssl` и `ca-certificates`. Пользователь-оператор должен иметь разрешение обращаться к
   Docker daemon.
3. Проверьте базовые инструменты:

```fish
docker version
docker compose version
git --version
curl --version
openssl version
```

4. Клонируйте репозиторий в native Linux filesystem. Не используйте Windows/shared mount:

```fish
git clone https://github.com/akiamuradev/arduino-component-knowledge-base.git
cd arduino-component-knowledge-base
git fetch --tags --prune
git checkout --detach <approved-full-commit-sha>
git rev-parse HEAD
```

`<approved-full-commit-sha>` берётся из утверждённого релиза, а не из непроверенной ветки.
Перед продолжением `git status --short` не должен показывать изменений исходного кода.

5. Установите edge/MinIO сертификаты и CA bundle вне репозитория с правами, указанными в
   [разделе TLS](DEPLOYMENT.md#2-внутренний-ca-и-сертификаты). Не копируйте private keys в
   checkout.

## 2. Настройка переменных окружения

Создайте production-файл только из версионированного шаблона:

```fish
umask 077
cp .env.production.example .env.production
chmod 600 .env.production
```

Редактируйте файл защищённым локальным редактором. Для каждого секрета создайте независимое
значение длиной не менее 32 URL-safe символов с помощью password manager или отдельного запуска
`openssl rand -hex 32`. Не передавайте секреты через аргументы команд, Git, chat или shell
history.

Группы настроек:

| Назначение | Переменные | Правило |
|---|---|---|
| PostgreSQL owner | `ACKB_POSTGRES_DB`, `ACKB_POSTGRES_USER`, `ACKB_POSTGRES_PASSWORD` | Только migrations и выдача grants |
| PostgreSQL runtime | `ACKB_POSTGRES_RUNTIME_USER`, `ACKB_POSTGRES_RUNTIME_PASSWORD` | Отдельная identity без DDL |
| PostgreSQL backup | `ACKB_POSTGRES_BACKUP_USER`, `ACKB_POSTGRES_BACKUP_PASSWORD` | Отдельная read-only identity |
| MinIO root | `ACKB_MINIO_ROOT_USER`, `ACKB_MINIO_ROOT_PASSWORD` | Только initial provisioning и recovery |
| MinIO runtime | `ACKB_MINIO_ACCESS_KEY`, `ACKB_MINIO_SECRET_KEY` | Не совпадает с root identity |
| Redis и auth | `ACKB_REDIS_PASSWORD`, `ACKB_AUTH_THROTTLE_PEPPER` | Два независимых секрета |
| Сеть | `ACKB_INTERNAL_HOSTNAME`, `ACKB_BIND_ADDRESS` | DNS должен указывать на static IP VM |
| TLS | `ACKB_EDGE_TLS_CERT_FILE`, `ACKB_EDGE_TLS_KEY_FILE`, `ACKB_MINIO_TLS_CERT_FILE`, `ACKB_MINIO_TLS_KEY_FILE`, `ACKB_CA_BUNDLE_FILE` | Только абсолютные пути; keys имеют mode `0400` или `0600` |
| Обработка файлов | `ACKB_FFPROBE_TIMEOUT_SECONDS`, `ACKB_FFMPEG_TIMEOUT_SECONDS`, `ACKB_FFMPEG_THREADS`, `ACKB_MEDIA_JOB_MAX_ATTEMPTS`, `ACKB_MEDIA_JOB_LEASE_SECONDS` | Сначала оставить проверенный template baseline |
| Импорт | `ACKB_IMPORT_JOB_MAX_ATTEMPTS`, `ACKB_IMPORT_LOCK_TTL_SECONDS`, `ACKB_IMPORT_LOCK_WAIT_SECONDS`, `ACKB_IMPORT_PIPELINE_MODE`, `ACKB_IMPORT_PIPELINE_STAGE_TIMEOUT_SECONDS`, `ACKB_IMPORT_PIPELINE_SAFE_RETRY_ATTEMPTS` | Для 1.0.0 authoritative switch не включать; baseline — `disabled` |
| KiCad shadow index | `ACKB_KICAD_INDEX_ARTIFACT_PATH`, `ACKB_KICAD_INDEX_EXPECTED_REVISION`, `ACKB_KICAD_INDEX_EXPECTED_SHA256` | Нужны только для отдельно принятого shadow mode |
| Production policy | `ACKB_LOG_LEVEL`, `ACKB_DOCS_ENABLED`, `ACKB_DATABASE_ECHO`, `ACKB_LEGACY_KICAD_CARD_IMPORT_ENABLED`, `ACKB_SESSION_COOKIE_SECURE`, `ACKB_SESSION_TTL_MINUTES` | Не ослаблять значения production template |
| Provenance | `ACKB_APP_VERSION`, `ACKB_COMMIT_SHA`, `ACKB_BUILD_DATE` | Версия релиза, полный lowercase SHA и UTC `YYYY-MM-DDTHH:MM:SSZ` |

Проверьте права файла и весь production contract. Preflight не меняет систему:

```fish
stat -c '%a %n' .env.production
./scripts/production_preflight.sh .env.production
```

Если preflight не прошёл, приложение не запускайте. Не обходите проверку временным отключением
TLS, secure cookies, trusted host или разделения database identities.

## 3. Запуск миграций

Обычный `$compose up` автоматически запускает одноразовые `migrate` и
`database-permissions`. Для контролируемой установки сначала соберите backend, поднимите
PostgreSQL и выполните эти шаги явно:

```fish
$compose build backend
$compose up -d --wait postgres
$compose run --rm --no-deps migrate
$compose run --rm --no-deps database-permissions
$compose run --rm --no-deps migrate alembic current
```

Для ACKB 1.0.0 ожидается единственный `20260729_28 (head)`. `Exited (0)` у одноразовых
`migrate`, `database-permissions`, `minio-identity-init` и `media-init` означает успех.

Не запускайте ORM `create_all`, не меняйте таблицы вручную и не отмечайте Alembic revision через
`stamp`, если миграция фактически не выполнена. При ошибке сохраните безопасный вывод
`$compose logs --tail 200 migrate database-permissions` и остановите обновление.

## 4. Создание первого администратора

После успешных migrations и grants создайте единственного первого администратора:

```fish
$compose run --rm --no-deps backend ackb-bootstrap-admin \
  --login <administrator-login> --display-name "<administrator-display-name>"
```

Команда дважды запросит пароль через TTY. Пароль содержит от 12 до 128 символов и не передаётся
аргументом. Bootstrap откажется работать, если активный administrator уже существует или login
занят. Дополнительных пользователей и временных редакторов создавайте только через защищённый UI.

После bootstrap войдите через browser и убедитесь, что доступна административная навигация.
Событие создания должно появиться в журнале действий.

## 5. Запуск приложения

После preflight и migrations запустите production stack:

```fish
$compose up --build -d
$compose ps -a
```

Runtime-сервисы `postgres`, `redis`, `minio`, `backend`, `worker`, `parser-worker`,
`job-reconciler`, `frontend` и `reverse-proxy` должны перейти в `Up`/`healthy`. Одноразовые
init-сервисы должны завершиться с code `0`. Наружу публикуются только static IP ports 80 и 443.

Для штатной остановки:

```fish
$compose stop reverse-proxy frontend backend worker parser-worker job-reconciler
```

Не используйте `down --volumes`: volumes содержат production PostgreSQL, Redis и MinIO data.

## 6. Проверка работоспособности

С VM проверьте Compose и HTTPS smoke:

```fish
$compose ps -a
set -x ACKB_SMOKE_BASE_URL "https://<internal-hostname>/"
set -x ACKB_SMOKE_CA_FILE /absolute/path/to/ca-bundle.crt
python3 scripts/production_smoke.py
```

Smoke проверяет `/health`, `/ready`, frontend, TLS hostname/CA, security headers и HTTP→HTTPS
redirect без insecure fallback. Дополнительно:

- с разрешённого клиентского ПК войдите, откройте каталог и загрузите небольшой тестовый файл;
- с внешнего VLAN подтвердите deny на 80/443;
- на VM убедитесь, что 5432, 6379, 9000 и 9001 не опубликованы;
- проверьте свободное место, срок TLS certificates и время последнего успешного backup;
- сохраните результат без credentials, cookies или содержимого карточек.

При неготовом `/ready` сначала смотрите состояние PostgreSQL и backend:

```fish
$compose logs --since 15m --tail 200 backend postgres reverse-proxy
```

Не публикуйте полный лог вне защищённого эксплуатационного контура: даже bounded logs могут
содержать идентификаторы задач и correlation IDs.

## 7. Резервное копирование

Полная точка восстановления состоит из согласованной пары:

1. PostgreSQL dump, manifest и SHA-256 sidecar;
2. snapshot Docker volume `minio-data` с binary media.

Redis не является источником истины: durable jobs хранятся в PostgreSQL и после восстановления
повторно доставляются reconciler. Checkout, `.env.production`, TLS keys и backup encryption keys
резервируются отдельно согласно политике организации.

Откройте окно без записи:

```fish
set backup_stamp (date -u +%Y%m%dT%H%M%SZ)
$compose stop reverse-proxy backend worker parser-worker job-reconciler
./scripts/database_backup.sh .env.production /var/backups/ackb $project
$compose stop minio
```

Пока writers и MinIO остановлены, сделайте storage-level snapshot точного volume:

```fish
set minio_volume "$project"_minio-data
docker volume inspect $minio_volume
set minio_mount (docker volume inspect --format '{{ .Mountpoint }}' $minio_volume)
string match -rq '^/var/lib/docker/volumes/[^/]+/_data$' $minio_mount; or exit 1
set minio_archive "/var/backups/ackb/ackb-minio-$backup_stamp.tar"
sudo tar --acls --xattrs --numeric-owner -C $minio_mount \
  -cpf $minio_archive .
sha256sum $minio_archive > "$minio_archive.sha256"
sudo chmod 600 $minio_archive
chmod 600 "$minio_archive.sha256"
```

Если resolved mountpoint пуст, равен `/` или не соответствует ожидаемому Docker volume path,
немедленно остановитесь. Для нестандартного Docker data-root используйте утверждённый
storage-level snapshot вместо адаптации команды наугад.

Возобновите сервисы и повторите smoke:

```fish
$compose up -d minio
$compose up -d backend worker parser-worker job-reconciler frontend reverse-proxy
$compose ps -a
```

Все PostgreSQL-файлы и MinIO archive/checksum одной точки пометьте общим timestamp, зашифруйте и
атомарно перенесите в off-host storage. Не отправляйте backup в Git. Baseline: daily PostgreSQL и
MinIO backup, 14 daily, 8 weekly, 12 monthly; ежемесячный и предрелизный restore drill. Если
организационный RPO меньше 24 часов, расписание должно быть строже.

## 8. Восстановление

Восстановление сначала репетируется в изолированной базе и никогда не перезаписывает production
автоматически. Найдите согласованную PostgreSQL/MinIO пару, проверьте оба checksum и зафиксируйте
исходную Alembic revision:

```fish
set dump /var/backups/ackb/ackb-postgresql-YYYYMMDDTHHMMSSZ.dump
sha256sum --check "$dump.sha256"
sha256sum --check /var/backups/ackb/ackb-minio-YYYYMMDDTHHMMSSZ.tar.sha256
./scripts/database_restore.sh \
  .env.production $dump ackb_restore_incident $project
```

Скрипт допускает только имя `ackb_restore_*`, проверяет dump/manifest, критичные данные и
Alembic upgrade, а production database не изменяет. Проверьте восстановленную базу отдельно до
cutover.

Восстановление MinIO выполняется только в согласованное downtime окно и только после сохранения
текущего повреждённого volume для расследования:

```fish
$compose down
set minio_volume "$project"_minio-data
set minio_mount (docker volume inspect --format '{{ .Mountpoint }}' $minio_volume)
string match -rq '^/var/lib/docker/volumes/[^/]+/_data$' $minio_mount; or exit 1
sudo find $minio_mount -mindepth 1 -maxdepth 1 -exec rm -rf -- '{}' '+'
sudo tar --acls --xattrs --numeric-owner --same-owner -C $minio_mount \
  -xpf /var/backups/ackb/ackb-minio-YYYYMMDDTHHMMSSZ.tar
```

Команда очистки необратима без archive. Перед ней второй оператор обязан сверить точные
`$project`, `$minio_volume`, `$minio_mount`, checksum и наличие отдельной копии повреждённого
volume. Никогда не подставляйте `/`, пустую переменную, glob или неразрешённый путь.

Переключение с production database на проверенную `ackb_restore_incident` не автоматизировано
намеренно. Его выполняет DBA через согласованный database cutover либо восстановление replacement
VM. Нельзя направлять старую и новую версии приложения в одну базу одновременно. После cutover:

```fish
$compose up --build -d
$compose run --rm --no-deps migrate alembic current
python3 scripts/production_smoke.py
```

Проверьте login, опубликованные карточки, изображения, audit и одну тестовую обработку. Старую
database/volume сохраняйте read-only до окончания rollback window.

## 9. Обновление с предыдущей версии

1. Прочитайте release notes и убедитесь, что исходная версия поддерживается.
2. Запишите текущий SHA, Alembic head, версии образов и Compose state:

```fish
git rev-parse HEAD
$compose run --rm --no-deps migrate alembic current
$compose images
$compose ps -a
```

3. Создайте согласованный PostgreSQL + MinIO backup по разделу 7.
4. Получите утверждённый commit без merge локальных изменений:

```fish
git fetch origin --tags --prune
git status --short
git checkout --detach <approved-new-full-commit-sha>
git rev-parse HEAD
```

5. Обновите только `ACKB_APP_VERSION`, `ACKB_COMMIT_SHA` и `ACKB_BUILD_DATE` в сохранённом
   `.env.production`; остальные secrets не заменяйте. Выполните preflight.
6. Соберите образы, выполните migrations и запустите stack:

```fish
./scripts/production_preflight.sh .env.production
$compose build backend frontend reverse-proxy
$compose up -d
$compose run --rm --no-deps migrate alembic current
```

7. Выполните production smoke и релевантные пункты
   [ручной приёмки](RELEASE_1.0.0_MANUAL_ACCEPTANCE.md). Не удаляйте старые images, checkout,
   database или MinIO snapshot до окончания rollback window.

## 10. Управление временными редакторами

Операция доступна только administrator:

1. Войдите и откройте `/admin/users` или пункт **Пользователи**.
2. Для новой учётной записи укажите уникальный login, отображаемое имя, временный пароль и
   будущую дату **Доступ редактора до**.
3. Для существующего активного пользователя задайте дату и нажмите **Назначить редактором**.
4. Для досрочного прекращения доступа нажмите **Отозвать досрочно**.
5. Для полной блокировки учётной записи используйте **Заблокировать** только после проверки
   выбранного пользователя.

После expiry или revoke редакторские permissions исчезают на backend, активные sessions
отзываются, а безопасная базовая роль пользователя сохраняется. Никогда не продлевайте доступ
изменением PostgreSQL вручную. Проверьте результат повторным входом и событиями
`Назначена роль редактора`/`Отозвана роль редактора` в журнале.

## 11. Просмотр журнала

Administrator открывает `/admin/audit` или пункт **Журнал действий**. Доступны фильтры по
пользователю, действию и диапазону дат, а также постраничный просмотр.

Журнал приложения содержит безопасную identity, действие, объект, время и результат. Raw
credentials, cookies, request details и содержимое карточек UI не показывает. В приложении нет
операции изменения или удаления audit events.

Для расследования:

1. зафиксируйте время события и отображаемый короткий object ID;
2. сузьте журнал по пользователю/действию/датам;
3. при необходимости сопоставьте время с bounded container logs;
4. сохраните только минимальный набор данных в защищённой заявке.

```fish
$compose logs --since 30m --tail 300 backend worker parser-worker job-reconciler
```

Не считайте Docker logs заменой audit log и не публикуйте их в открытой системе заявок.

## 12. Действия при ошибке обработки компонентов

Administrator открывает `/admin/jobs` (**Диагностика**) и выбирает состояние **Ошибки**.
Редактор видит собственные загрузки на `/admin/import`, но не общий monitor.

1. Определите тип: импорт компонента, изображение или видео.
2. Запишите короткий job ID, время, попытку и безопасное русское сообщение.
3. Проверьте `$compose ps -a` и соответствующий worker:

```fish
$compose logs --since 15m --tail 200 job-reconciler worker parser-worker
```

4. Если job остался в очереди после восстановления Redis/worker, выполните один раз:

```fish
$compose run --rm job-reconciler ackb-reconcile-jobs
```

5. Если UI показывает кнопку **Повторить**, устраните внешнюю причину и запросите один ручной
   retry. Для validation/rejected ошибки исправьте исходные данные и создайте новую загрузку.
6. Убедитесь, что статус изменился, draft не опубликован автоматически, а retry записан в audit.

Не меняйте job status в PostgreSQL, не добавляйте сообщение напрямую в Redis и не запускайте
бесконечные retry. После исчерпания attempts сохраните correlation/job ID и передайте инцидент
разработчику без файла пользователя и внутренних credentials.

## 13. Откат выпуска

Откат выполняется при неустранимой ошибке запуска, миграции, безопасности или потере критичного
сценария. До обновления должны существовать согласованные pre-upgrade PostgreSQL/MinIO backup,
старый full commit SHA и старые images.

1. Остановите входящий трафик и writers, сохраните диагностику:

```fish
$compose stop reverse-proxy backend worker parser-worker job-reconciler
$compose ps -a
$compose logs --since 30m --tail 300 migrate backend worker parser-worker
```

2. Если после обновления ещё не было business writes формата 1.0.0 и release notes подтверждают
   обратимый schema rollback, выполните downgrade кодом новой версии до предыдущего ACKB 0.21.0
   head:

```fish
$compose run --rm --no-deps migrate alembic downgrade 20260721_16
$compose run --rm --no-deps migrate alembic current
```

Downgrade ACKB 1.0.0 удаляет новые 1.0.0 tables и поля, включая предложения исправлений,
editor grant history и новые import/review данные. Не выполняйте его после открытия writers:
перейдите сразу к восстановлению согласованной pre-upgrade пары. Даже до открытия writers
downgrade допустим только при наличии проверенного pre-upgrade dump.

3. Верните утверждённый старый checkout без переписывания истории:

```fish
git checkout --detach <approved-previous-full-commit-sha>
git rev-parse HEAD
```

4. Верните старые `ACKB_APP_VERSION`, `ACKB_COMMIT_SHA`, `ACKB_BUILD_DATE`, не меняя secrets,
   выполните preflight, пересоберите и запустите:

```fish
./scripts/production_preflight.sh .env.production
$compose build backend frontend reverse-proxy
$compose up -d
python3 scripts/production_smoke.py
```

Если downgrade не завершился или состояние PostgreSQL/MinIO уже расходится, не продолжайте
in-place rollback. Восстановите согласованную pre-upgrade пару по разделу 8 на replacement VM или
через согласованный DBA cutover. Не используйте `git reset --hard`, `down --volumes`, ручное
редактирование schema или частичное восстановление только PostgreSQL.

После отката проверьте login всех требуемых ролей, каталог, изображения, создание draft, audit и
диагностику. Сохраните неудачную версию и её данные изолированно до завершения расследования.
