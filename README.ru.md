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
Текущая версия — **1.7.5**.

Автор и разработчик — [akiamuradev](https://github.com/akiamuradev).

Чистая установка содержит категории и описания разрешённых источников, но не вымышленные и не
автоматически опубликованные карточки. Импорт всегда начинает работу с черновика; материал
становится видимым студентам только после проверки, одобрения и явной публикации.

## Возможности ACKB

- Русскоязычное рабочее пространство на всю ширину desktop с адаптивным mobile layout:
  поиск по каталогу, фильтры по категории/сложности, карточки компонентов и галереи изображений.
- Контролируемый путь черновик → проверка → одобрение → явная публикация, неизменяемые
  опубликованные снимки, история ревизий, скрытие/архив и отдельные предложения преподавателя.
- Синхронизируемый редактор карточек с optimistic edit tokens и обработкой конфликтов;
  структурированные diagnostics валидации, переход к полям и явное преобразование совместимых
  единиц характеристик. Руководство по заполнению доступно после входа и открывается в отдельной
  вкладке, не заменяя черновик.
- Серверные роли `student`, `teacher`, временный `editor` и `administrator`; регистрация только
  студентов, управление аккаунтами/паролями администратором, показ/скрытие пароля и опциональное
  запоминание входа на устройстве.
- Светлая, тёмная и системная темы, RGB/HEX-акценты и сохранённые в браузере пользовательские
  пресеты. Фирменные цвета независимы от UI-акцентов.
- Публичная страница `/license` с полным текстом GNU GPL и нейтральные блоки образовательных
  организаций со ссылками на МПК ЛГПУ и ЛГПУ.
- Импортёр legacy ZIP/XLSX: закрытая загрузка исходников, анализ до применения, проверка
  администратором, явное подтверждение плана и применение только в черновики. Права на материалы
  проверяются до публикации; см. [руководство импортёра](docs/LEGACY_IMPORTER.md).
- Exact/fuzzy-кандидаты в дубликаты с решением об объединении только администратором.
  Зарегистрированные адаптеры Seeed Studio Wiki/KiCad Symbols сохраняют provenance и снимки
  лицензий, но внешние источники **неактивны для нового импорта**. Evidence-first pipeline
  остаётся в **disabled/shadow**, а не основным production-путём импорта.
- Private MinIO с проверкой и обработкой изображений/видео; durable dispatch на PostgreSQL,
  Redis/Dramatiq workers и reconciliation прерванных заданий.
- Аудит, Argon2id, opaque server-side sessions, CSRF-защита и постоянный login throttling;
  backend всегда остаётся источником истины для авторизации.
- Сборка образов с реальной provenance, Alembic, production preflight и deployment smoke checks,
  процедуры backup/restore PostgreSQL и закрытого объектного хранилища.

Это возможности реализованного кода, а не подтверждение развёрнутого релиза. Release gate описан ниже.

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

Нужны Docker Engine, Docker Compose plugin, Git, Python 3.12+, `curl` и `openssl`. Клонируйте основную ветку в
нативную Linux filesystem:

```bash
git clone --branch main --single-branch \
  https://github.com/akiamuradev/arduino-component-knowledge-base.git
cd arduino-component-knowledge-base
bash scripts/linux_bootstrap.sh
```

Bootstrap создаёт ignored `.env` со случайными локальными credentials и правами `0600`, проверяет
Compose, собирает образы через `python3 scripts/build_images.py`, запускает их командой
`docker compose up --no-build --detach` и ждёт health checks. Секреты в вывод не попадают.
Откройте <http://localhost:8080>.

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
docker compose config --quiet
python3 scripts/build_images.py
docker compose up --no-build --detach
python3 scripts/compose_smoke.py
```

Не заменяйте `.env`, если используете существующий PostgreSQL volume. Production-развёртывание,
backup, restore и обновление описаны в [руководстве по эксплуатации](docs/OPERATIONS.md).
Команды выше относятся к локальному stack, а не заменяют production-процедуру. Сборщик требует
чистый закоммиченный checkout, получает версию из project metadata и полный SHA из Git;
старые значения `.env` не могут переопределить build metadata сайта.

## Создание первого администратора

После успешного запуска:

```bash
docker compose run --rm backend ackb-bootstrap-admin \
  --login admin --display-name "Initial Administrator"
```

Введите пароль дважды через TTY. Он должен содержать 12–128 символов и никогда не передаётся
аргументом командной строки. Bootstrap доступен только пока в базе нет активного администратора.

Студент регистрируется на `/register` только с логином и паролем; backend назначает роль `student`.
Существующие администраторы сбрасывают пароли и создают дополнительных администраторов в защищённом
workspace. Сброс пароля отзывает все сессии пользователя. Самостоятельного восстановления, сбора
email/телефона, 2FA и recovery codes нет.

## Основной workflow

1. Редактор или администратор создаёт ручной черновик. Зарегистрированные adapters Seeed/KiCad
   доступны для контролируемой проверки, но их источники неактивны для новых import jobs.
2. Отдельный legacy ZIP/XLSX workflow анализирует закрытый набор и требует проверки администратором
   и текстового подтверждения перед применением плана. Repository import требует явной активации
   источника после утверждения policy. Ни один путь не публикует автоматически.
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
[документе о тестировании](docs/TESTING.md). Workflow `quality` запускает обязательные CI checks
на каждый push и pull request; он не развёртывает и не проверяет production.

Обновление четырёх README screenshots из детерминированных test-only fixtures (из `frontend`):

```bash
ACKB_UPDATE_SCREENSHOTS=1 npm run test:e2e -- --grep "captures approved responsive theme views"
```

Изображения документируют UI, но не заменяют layout assertions и production-проверки.

## Release и deployment gate

Релиз завершён только когда **все обязательные GitHub CI checks успешны**, разрешённый deployment
после merge в `main` успешен и проверен фактический production build. Running containers,
production smoke и metadata сайта/API сверяются с deployed checkout: реальная версия, полный Git
SHA и фактическое время сборки. Frontend `/build-info.json` описывает собранный артефакт,
backend `/health` возвращает версию приложения (не SHA и время сборки). Устаревшее или несовпадающее значение оставляет
релиз незавершённым, даже если приложение работает.

Локальные тесты, CHANGELOG, tags, GitHub Releases и merge PR не заменяют эту проверку. В отчёте
обязательны version, full commit SHA, build date, CI status, production smoke result и подтверждение,
что production обслуживает именно этот build. Если deployment не разрешён, не выполнять его и явно
оставить production gate открытым. Полный workflow — в [CONTRIBUTING.md](CONTRIBUTING.md) и
[руководстве эксплуатации](docs/OPERATIONS.md).

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
