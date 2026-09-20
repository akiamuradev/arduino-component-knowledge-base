# Arduino Component Knowledge Base

[![Quality](https://github.com/akiamuradev/arduino-component-knowledge-base/actions/workflows/quality.yml/badge.svg?branch=main)](https://github.com/akiamuradev/arduino-component-knowledge-base/actions/workflows/quality.yml?query=branch%3Amain)
[![Лицензия: GNU GPL v3.0 or later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue)](LICENCE)

[![Тесты: есть](https://img.shields.io/badge/Tests-included-success)](docs/TESTING.md)

![Python](https://img.shields.io/badge/Python-3776AB)
![React](https://img.shields.io/badge/React-149ECA)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6)
![Vite](https://img.shields.io/badge/Vite-646CFF)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![Pydantic](https://img.shields.io/badge/Pydantic-E92063)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00)
![asyncpg](https://img.shields.io/badge/asyncpg-336791)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1)
![Alembic](https://img.shields.io/badge/Alembic-555555)
![Redis](https://img.shields.io/badge/Redis-DC382D)
![Dramatiq](https://img.shields.io/badge/Dramatiq-555555)
![MinIO](https://img.shields.io/badge/MinIO-C72E49)
![Pillow](https://img.shields.io/badge/Pillow-3776AB)
![FFmpeg](https://img.shields.io/badge/FFmpeg-007808)
![nginx](https://img.shields.io/badge/nginx-009639)
![Docker Compose](https://img.shields.io/badge/Docker%20Compose-2496ED)

**[English](README.md) · Русский**

Самостоятельный образовательный каталог проверенных сведений об Arduino-совместимых платах,
датчиках, исполнительных устройствах, дисплеях и других электронных компонентах.

## О проекте

Arduino Component Knowledge Base (ACKB) предоставляет студентам каталог с поиском, а
преподавателям, редакторам и администраторам — контролируемый процесс подготовки материалов.
Текущая версия — **1.6.1**.

Автор и разработчик — [akiamuradev](https://github.com/akiamuradev).

Чистая установка содержит категории и описания разрешённых источников, но не вымышленные и не
автоматически опубликованные карточки. Импорт всегда начинает работу с черновика; материал
становится видимым студентам только после проверки, одобрения и явной публикации.

## Главное в v1.0.0

- адаптивный русскоязычный React-интерфейс со светлой, тёмной и системной темами;
- поиск, фильтры по категории и сложности, страницы компонентов и галереи изображений;
- серверные роли студентов, преподавателей, временных редакторов и администраторов;
- черновики, проверка, одобрение, публикация, скрытие, архив и неизменяемая история ревизий;
- предложения исправлений от преподавателей без прямой перезаписи опубликованного материала;
- versioned adapters Seeed Studio Wiki и KiCad Symbols с сохранением provenance и снимка лицензии; все источники сейчас неактивны для нового импорта;
- exact/fuzzy-поиск дубликатов и подтверждение merge только администратором;
- private MinIO, проверка и обработка изображений/видео, надёжные Redis/Dramatiq jobs;
- аудит действий, Argon2id, opaque sessions, CSRF-защита и throttling;
- воспроизводимый Docker Compose, Alembic, backup, restore и проверки обновления.

## Скриншоты

| Каталог — светлая тема | Каталог — тёмная тема |
|---|---|
| ![Каталог ACKB в светлой теме](docs/screenshots/frontend-light-desktop.png) | ![Каталог ACKB в тёмной теме](docs/screenshots/frontend-dark-desktop.png) |

| Вход — мобильная светлая тема | Вход — мобильная тёмная тема |
|---|---|
| ![Страница входа ACKB на мобильном экране в светлой теме](docs/screenshots/frontend-light-mobile.png) | ![Страница входа ACKB на мобильном экране в тёмной теме](docs/screenshots/frontend-dark-mobile.png) |

Скриншоты создаёт детерминированный Playwright-сценарий репозитория; production-код не содержит
тестовых данных каталога.

## Архитектура

| Слой | Технологии |
|---|---|
| Web-интерфейс | React 19, TypeScript 6, Vite |
| API и авторизация | FastAPI, Pydantic, SQLAlchemy 2, asyncpg |
| Постоянные данные | PostgreSQL 17 и миграции Alembic |
| Медиа | Private MinIO, Pillow, FFmpeg |
| Фоновые задачи | Redis 8 и Dramatiq |
| Edge | nginx и Docker Compose |

```text
Браузер -> reverse proxy -> frontend
                          -> backend -> PostgreSQL
                                     -> Redis -> workers
                                     -> private MinIO
```

Backend является источником истины для авторизации. Parser не может опубликовать карточку, а
merge дубликатов всегда требует отдельного решения администратора. Полное описание:
[архитектура](docs/ARCHITECTURE.md) и [безопасность](docs/SECURITY.md).

## Быстрый запуск

Нужны Docker Engine, Docker Compose plugin, Git, `curl` и `openssl`. Клонируйте основную ветку в
нативную Linux filesystem:

```bash
git clone --branch main --single-branch \
  https://github.com/akiamuradev/arduino-component-knowledge-base.git
cd arduino-component-knowledge-base
bash scripts/linux_bootstrap.sh
```

Bootstrap создаёт ignored `.env` со случайными локальными credentials и правами `0600`, собирает
stack и ждёт health checks. Секреты в вывод не попадают. Откройте <http://localhost:8080>.

Проверка:

```bash
docker compose ps -a
curl -f http://127.0.0.1:8080/health
curl -f http://127.0.0.1:8080/ready
python3 scripts/compose_smoke.py
```

`migrate` и `media-init` — одноразовые services; `Exited (0)` означает успех. Для существующей
копии релиза сохраните её `.env` и volumes:

```bash
git pull --ff-only origin main
docker compose up --build -d
python3 scripts/compose_smoke.py
```

Не заменяйте `.env`, если используете существующий PostgreSQL volume. Production-развёртывание,
backup, restore и обновление описаны в [руководстве по эксплуатации](docs/OPERATIONS.md).

## Создание первого администратора

После успешного запуска:

```bash
docker compose run --rm backend ackb-bootstrap-admin \
  --login admin --display-name "Initial Administrator"
```

Введите пароль дважды через TTY. Он должен содержать 12–128 символов и никогда не передаётся
аргументом командной строки. Bootstrap доступен только пока в базе нет активного администратора.

## Основной workflow

1. Редактор или администратор создаёт ручной черновик. Зарегистрированные adapters Seeed/KiCad
   доступны для контролируемой проверки, но их источники неактивны для новых import jobs.
2. Если источник явно активирован после утверждения policy, выбранный элемент импорта становится
   черновиком и никогда не публикуется автоматически.
3. Редактор завершает карточку и разбирает кандидатов в дубликаты.
4. Редактор отправляет материал на проверку; администратор возвращает его или одобряет.
5. Администратор явно публикует одобренную ревизию.
6. Студенты видят неизменяемый опубликованный snapshot. Новые изменения создают отдельный
   черновик; скрытие и архивирование остаются обратимыми.

## Разработка и проверки

В проекте есть автоматические backend, frontend, интеграционные и браузерные тесты; см. [Тестирование](docs/TESTING.md).

Используйте Python 3.12 или новее, [uv](https://docs.astral.sh/uv/), Node.js `>=22.12 <26`, npm и
Docker.

Проверки backend и документации:

```bash
uv lock --check
uv sync --frozen --extra dev
uv run ruff check .
uv run ruff format --check src scripts tests migrations
uv run mypy --strict src scripts tests migrations
uv run pytest
uv run python -m build
uv run python scripts/docs_contract.py
uv run python scripts/release_contract.py
uv run python scripts/backend_smoke.py
```

Проверки frontend и browser:

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

Container checks и окружение PostgreSQL/MinIO integration описаны в
[документе о тестировании](docs/TESTING.md). Workflow `quality` запускает полный обязательный
release gate на каждый push и pull request.

## Документация

- [Требования](docs/REQUIREMENTS.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [Модель данных](docs/DATA_MODEL.md)
- [Тестирование](docs/TESTING.md)
- [Контроли безопасности](docs/SECURITY.md) и [модель угроз](docs/THREAT_MODEL.md)
- [Эксплуатация](docs/OPERATIONS.md) и [развёртывание](docs/DEPLOYMENT.md)
- [Проверка импорта](docs/IMPORT_VALIDATION.md) и [ROADMAP импорта](docs/imports/ROADMAP.md)
- [Лицензирование данных](docs/DATA_LICENSING.md) и [сторонние материалы](THIRD_PARTY_NOTICES.md)
- [Участие в разработке и fork](CONTRIBUTING.md)

## Участие в разработке и fork

Чтобы отправить изменение в исходный проект, создайте fork на GitHub, клонируйте его, добавьте
этот репозиторий как `upstream` и создайте ветку от `upstream/main`:

```bash
git clone https://github.com/<username>/arduino-component-knowledge-base.git
cd arduino-component-knowledge-base
git remote add upstream https://github.com/akiamuradev/arduino-component-knowledge-base.git
git fetch upstream
git switch -c feature/<short-name> upstream/main
```

Не отправляйте изменения напрямую в `main`. Один PR должен решать одну
ограниченную задачу. Синхронизируйтесь через `git fetch upstream` и запускайте подходящие проверки
перед PR. Никогда не коммитьте `.env`, credentials, generated build output и пользовательские
данные.

Независимый fork или производный проект остаётся под
[GNU General Public License v3.0 or later](LICENCE).
Импортированные данные сохраняют собственные лицензии, attribution и provenance. Перед публичным
deployment замените credentials и выполните требования безопасности и развёртывания. Не создавайте
впечатление официальной связи с Arduino, Seeed Studio, KiCad или akiamuradev. При переименовании
согласованно обновите branding, package metadata, Compose image names, frontend metadata, версии и
документацию.

Полные сценарии исходного и независимого fork: [CONTRIBUTING.md](CONTRIBUTING.md).

## Безопасность

Не публикуйте credentials, персональные данные и детали эксплуатации уязвимости в issue или pull
request. Перед изменением authentication, imports, media или deployment изучите границы доверия в
[документе о безопасности](docs/SECURITY.md). Зелёный CI не заменяет TLS, ротацию secrets, backup,
network policy, monitoring и production preflight.

## Лицензия и сторонние материалы

Код приложения распространяется по
[GNU General Public License v3.0 or later](LICENCE). SPDX: `GPL-3.0-or-later`. Автор: akiamuradev.

Импортированные сторонние материалы не перелицензируются как код приложения. Требования к
лицензиям, attribution и provenance описаны в
[лицензировании данных](docs/DATA_LICENSING.md) и
[уведомлениях о сторонних материалах](THIRD_PARTY_NOTICES.md).
