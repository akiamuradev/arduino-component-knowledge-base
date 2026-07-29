# Протокол проверки обновления ACKB 1.0.0

Дата: 2026-07-29. Исходная версия: тег `v0.21.0`, Alembic
`20260721_16`. Целевая версия: `1.0.0`, Alembic `20260729_27`.

Проверка выполнена только на одноразовых PostgreSQL databases и отдельном production-like
Compose project. Рабочая локальная база и производственный сервер не изменялись.

## Результат

Обновление ACKB `0.21.0 -> 1.0.0` прошло без потери проверяемых данных. Сохранённые учётные
записи вошли с прежними паролями, роли остались действующими, старая карточка, её revision
history, импорт и audit event сохранились. После обновления временный редактор создал новую
загрузку и карточку, администратор одобрил и опубликовал карточку.

Оба предусмотренных пути отката подтверждены:

- in-place downgrade новой схемой с `20260729_27` до `20260721_16` до появления записей
  формата 1.0.0;
- восстановление проверенного pre-upgrade custom dump в отдельную базу с исходным Alembic
  revision и идентичной сигнатурой критичных данных.

## Матрица проверки

| Требование | Проверка | Результат |
|---|---|---|
| Резервная копия до обновления | `pg_dump --format=custom`, mode `0600`, непустой файл, `pg_restore --list`, SHA-256 verify | пройдено |
| Применение миграций | точный tagged head `20260721_16` обновлён до единственного head `20260729_27` | пройдено |
| Пользователи | UUID, login, имя, статус и password hash сохранены | пройдено |
| Карточки | UUID, slug, содержимое, категория, статус и revision сохранены | пройдено |
| История | старая revision сохранена; migration добавила безопасные action и summary | пройдено |
| Роли | administrator и student grants сохранены; новые lifetime-поля применены | пройдено |
| Вход администратора | прежний login/password, server-side role и permissions | пройдено |
| Вход обычного пользователя | прежний login/password, только `components.view` | пройдено |
| Временный редактор | выдача `student + editor`, срок действия и вход | пройдено |
| Загрузка компонентов | editor создал repository import через защищённый API; job получил `queued` | пройдено |
| Редакционный цикл | editor создал draft и отправил на review; administrator одобрил и опубликовал | пройдено |
| Откат | downgrade до `20260721_16` и отдельный restore pre-upgrade dump | пройдено |

Сигнатура upgrade-drill строится только по полям, существующим в обеих версиях, для users,
role grants, components, component revisions, import jobs и audit events. Она совпала до
миграции, после upgrade, после downgrade и после восстановления dump.

## Воспроизведение

Основной production-like сценарий:

```bash
bash scripts/database_restore_smoke.sh
```

API acceptance входит в integration suite:

```bash
ACKB_RUN_INTEGRATION=1 uv run pytest \
  tests/integration/test_release_upgrade_postgresql.py --strict-markers
```

Drill сам создаёт и удаляет временные databases, credentials, Docker network и volume. Fixture
[`upgrade-0.21.0-seed.sql`](../deploy/postgres/upgrade-0.21.0-seed.sql) намеренно совместим
только со схемой опубликованного `0.21.0`, поэтому случайный старт с более новой миграции
обнаруживается.

## Границы протокола

PostgreSQL drill не заменяет согласованный backup MinIO. Перед реальным обновлением нужно
остановить writers и создать пару PostgreSQL dump + MinIO snapshot по `OPERATIONS.md`.
Внешний сетевой parser в этом сценарии не запускается: проверяется приём задания, сохранность
старого import job и остальной детерминированный parser test suite. Проверка на production
разрешается только отдельным решением владельца системы.

Итог этапа: критерии обновления и отката для release candidate `1.0.0` выполнены.
