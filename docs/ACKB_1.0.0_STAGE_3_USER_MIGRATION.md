# ACKB 1.0.0 — проверка миграции существующих пользователей

## Назначение

Миграция `20260728_21` переносит существующие учётные записи на безопасную модель ролей:

- действующие `administrator`, `teacher`, `student` и явно выданные непросроченные `editor`
  сохраняются без изменений;
- пользователь без действующей базовой роли (`student`, `teacher` или `administrator`) получает
  только `student`;
- пользователь только с непросроченным `editor` получает базовый `student`, а временный
  `editor` сохраняется до своего срока;
- пользователь только с истёкшим `editor` или отозванными grants получает `student`, а прежние
  строки остаются в истории;
- миграция никогда не создаёт `teacher`, `editor` или `administrator`;
- после backfill встроенная SQL-проверка прерывает transaction, если хотя бы один пользователь
  остался без действующей базовой роли.

Backfill grant имеет детерминированный UUID из префикса `ackb-1.0.0-safe-student:` и
`user_id`. Поэтому downgrade до `20260728_20` удаляет только созданные этой миграцией строки.

## Проверка на копии production-базы

Не проверяйте downgrade на рабочей базе. Создайте зашифрованный backup, восстановите его в
изолированном PostgreSQL без доступа приложения и ограничьте доступ к файлу: дамп содержит
логины, password hashes и другие персональные данные.

Пример создания backup в fish; подставьте production Compose files и реальные имена базы и
пользователя:

```fish
umask 077
set backup_file "ackb-before-role-migration-"(date -u +%Y%m%dT%H%M%SZ)".dump"
docker compose exec -T postgres \
  pg_dump --format=custom --no-owner --no-acl --username ackb ackb > $backup_file
sha256sum $backup_file > $backup_file.sha256
```

Восстановите дамп в отдельный disposable database/Compose project. Не подключайте к нему
backend, workers или parser-worker. Затем:

1. Проверьте backup командой `pg_restore --list`.
2. Обновите копию только до `20260728_20`.
3. Сохраните результаты контрольных запросов ниже в защищённом журнале.
4. Выполните `alembic upgrade 20260728_21`.
5. Повторите запросы и сравните результаты.
6. Войдите тестовой копией существующего администратора и пользователя с backfill `student`.
7. Только на disposable copy выполните `alembic downgrade 20260728_20`, затем снова
   `alembic upgrade 20260728_21`.

Команды миграции для запущенного изолированного Compose project:

```fish
docker compose run --rm --no-deps backend alembic upgrade 20260728_20
docker compose run --rm --no-deps backend alembic current
docker compose run --rm --no-deps backend alembic upgrade 20260728_21
docker compose run --rm --no-deps backend alembic current
```

## Контрольные запросы

До и после `20260728_21` количество и fingerprint действующих администраторов должны совпадать:

```sql
SELECT
    count(DISTINCT user_id) AS administrator_count,
    md5(coalesce(string_agg(DISTINCT user_id::text, ',' ORDER BY user_id::text), ''))
        AS administrator_fingerprint
FROM user_roles
WHERE role = 'administrator'
  AND revoked_at IS NULL;
```

После миграции запрос должен вернуть `0` — у каждого пользователя есть безопасная базовая роль,
которая останется после истечения временного `editor`:

```sql
SELECT count(*) AS users_without_active_baseline_role
FROM users
WHERE NOT EXISTS (
    SELECT 1
    FROM user_roles
    WHERE user_roles.user_id = users.id
      AND user_roles.revoked_at IS NULL
      AND user_roles.role IN ('student', 'teacher', 'administrator')
);
```

Миграция может создать только `student`; запрос должен вернуть `0`:

```sql
SELECT count(*) AS unsafe_backfill_roles
FROM user_roles
WHERE id = md5('ackb-1.0.0-safe-student:' || user_id::text)::uuid
  AND role <> 'student';
```

Количество безопасных backfill grants доступно без вывода пользовательских данных:

```sql
SELECT count(*) AS safe_student_backfills
FROM user_roles
WHERE id = md5('ackb-1.0.0-safe-student:' || user_id::text)::uuid
  AND role = 'student'
  AND granted_by IS NULL;
```

Отдельно проверьте, что строки `editor` с прошедшим `expires_at` и строки с ненулевым
`revoked_at` не удалились. Их количество после upgrade не должно уменьшиться.

## Критерии допуска

- Alembic показывает `20260728_21 (head)`.
- Ни один пользователь не остался без действующей базовой роли.
- Состав действующих администраторов совпадает с состоянием на `20260728_20`.
- Backfill создал только `student`.
- Исторические expired/revoked grants сохранились.
- Существующий администратор может войти.
- Пользователь, которому требовался backfill, входит с минимальными правами `student`.

Если любой критерий нарушен, не обновляйте production. Сохраните копию базы и вывод проверки
без password hashes, cookies и секретов, затем разберите расхождение до повторной миграции.
