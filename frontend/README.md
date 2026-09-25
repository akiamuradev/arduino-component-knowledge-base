# Frontend

React + strict TypeScript приложение на Vite. Оно обращается только к same-origin `/api/v1`,
использует opaque cookies backend и не хранит session tokens или роли в localStorage. Backend
остаётся единственным источником истины для permissions.

## Структура

- `src/api` — типизированные HTTP contracts, общий client, CSRF и typed errors;
- `src/auth` — TanStack Query для backend-resolved principal и проверки permissions;
- `src/app/navigation.ts` — единый permission-based контракт основной и редакционной навигации;
- `src/routing` — authentication/role UX guards; они не являются security boundary;
- `src/layouts` — student и administrator shells;
- `src/pages` — route-level страницы;
- `src/workspace` — queries для dashboard, карточек и категорий;
- `src/jobs` — administrator-only polling и retry mutations для durable job monitor;
- `src/components` — общие состояния, header/footer, карточки, media/provenance и OLED;
- `src/theme` — темы `light`, `dark`, `system` с системной подпиской и persistence;
- `src/config/brand.ts` — неизменяемые product identity и build metadata.

## Product UI

- дизайн использует централизованные CSS-токены графитово-бежевой палитры и акцент `#32CD32`;
- тема и акценты хранят косметические предпочтения в `ackb-ui-preferences` с миграцией
  старого `ackb-theme`; права и auth state туда не записываются;
- оформление выбирается одной доступной кнопкой с меню, единым набором SVG-иконок и вариантами
  «Светлое», «Тёмное», «Как на устройстве»; меню поддерживает клавиатурную навигацию;
- `/about` показывает автора `akiamuradev`, фактическую GNU GPL v3.0 or later License,
  репозиторий и build info;
- login OLED собран из HTML/CSS/SVG, использует один `requestAnimationFrame`, CSS variables,
  reduced-motion и не участвует в проверке credentials или roles;
- global search передаёт `q` в реальный catalog endpoint через URL.
- шапка показывает серверное имя и русское название роли, а ссылки фильтруются только по
  permissions из `/auth/me`; на мобильном экране основная навигация остаётся доступной;
- редакционная навигация разделяет работу с материалами и административные инструменты.

Published catalog API отдаёт metadata медиа и источников из опубликованного снимка.
`MediaGallery` и `SourceAttributionBlock` появляются при наличии соответствующих данных;
frontend не создаёт фиктивные production-данные. `/sources` показывает реестр источников,
включая неактивные, без автоматического разрешения импорта.

## Editorial workspace contract

Маршруты `/admin`, `/admin/components`, `/admin/components/new` и
`/admin/components/:id/edit` доступны editor/administrator по серверным permissions. Teacher
остаётся в опубликованном каталоге и может отправить отдельное предложение исправления. Frontend
ожидает:

- `GET /api/v1/workspace/components`;
- `GET /api/v1/workspace/categories`;
- `GET|PUT /api/v1/workspace/components/{id}`;
- `GET /api/v1/workspace/components/{id}/correction-proposals`;
- `POST /api/v1/workspace/components`;
- `POST /api/v1/catalog/components/{id}/correction-proposals`;
- `POST /api/v1/workspace/components/{id}/correction-proposals/{proposal_id}/resolve`;
- `POST /api/v1/workspace/components/{id}/publish`;
- `POST /api/v1/workspace/components/{id}/archive`.

Все mutations включают CSRF. Редактор синхронизируется через
`POST /api/v1/workspace/components/{id}/sync` с optimistic `edit_token`; переходы workflow
выполняются через server-owned команды. Конфликт не перезаписывает локальную форму:
пользователь сверяет изменения с серверной версией. Backend реализует эти endpoints и
проверяет permissions независимо от frontend guards.

Маршрут `/admin/jobs` дополнительно защищён administrator UX guard и ожидает
`GET /api/v1/admin/jobs` и CSRF-protected `POST /api/v1/admin/jobs/{id}/retry`. Backend RBAC
остаётся обязательной границей; список обновляется каждые пять секунд и не подменяется mock data.

## Настройки сайта

Общая панель в шапке, на входе и регистрации управляет темой и акцентом. Пять
пресетов: ACKB Green `#32CD32`, Cyan `#23C6D8`, Blue `#4C8DFF`, Violet `#A970FF`,
Orange `#FF9D3D`. «Свой цвет» открывает круг оттенка/насыщенности, яркость и
синхронизированные HEX/RGB-поля; они доступны без мыши. Невалидный ввод остаётся
черновиком и не заменяет последний допустимый цвет.

`ThemeProvider` хранит только косметические настройки в `ackb-ui-preferences`:

```json
{"version":2,"theme":"system","accent":{"type":"preset","value":"green"},"savedAccents":[]}
```

«Сохранить цвет» добавляет текущий допустимый custom-акцент в «Мои цвета»: до 12
уникальных цветов в порядке добавления. HEX нормализуется в `#RRGGBB`; некорректные
записи отбрасываются. При ошибках в HEX/RGB, повторе или полной палитре сохранение
недоступно. Удаление сохранённого цвета не меняет активный акцент. Схема v1
автоматически становится v2 с пустым `savedAccents`, без потери темы и акцента.

Пользовательский акцент: `{"type":"custom","value":"#B45CFF"}`. При первом
запуске старое `ackb-theme` автоматически переносится в новую структуру. После
миграции приоритет у новой записи; старый ключ не удаляется. Неизвестная версия или
повреждённые данные безопасно возвращают старую тему / системную тему и зелёный
акцент. При недоступном localStorage настройки работают до перезагрузки страницы.
В backend они не отправляются и с учётной записью не связываются.

`colors.ts` выводит контрастные CSS-токены из одного RGB-цвета. Брендовые
`--color-brand` / `--color-brand-bright`, PCB/OLED-иллюстрации, подсветка синтаксиса
и семантические статусы независимы от UI-акцента. Нативный диалог обеспечивает
клавиатурный фокус, Escape и возврат к кнопке; на узком экране панель прокручивается
в пределах viewport. Миграция БД и изменение API не нужны.

## Локальный запуск

Публичный `/license` не требует сессии. Полный юридический текст статически
встраивается при сборке из `public/LICENCE.txt`: Vite и `scripts/build_images.py`
проверяют точное совпадение с каноническим `LICENCE` в корне репозитория.
Существующая release-contract проверка также сохраняется. Разметка делит текст
только на абзацы и заголовки, не меняя слов, пунктуации и нумерации; исходный
`/LICENCE.txt` остаётся доступен. Оглавление строится из тех же заголовков.

```bash
npm ci
npm run dev
```

Vite проксирует `/api` на `http://127.0.0.1:8000`. Production должен публиковать frontend и
backend через один reverse proxy origin. `VITE_API_BASE_URL`, если задан, обязан быть
same-origin абсолютным path, например `/api/v1`; URL внешнего origin отклоняется при старте.

Версия берётся из `package.json`, согласованного с `pyproject.toml` release-проверкой;
коммит — из фактического Git HEAD, дата UTC — из текущего запуска сборки. Старые
`VITE_APP_VERSION`, `VITE_COMMIT_SHA`, `VITE_BUILD_DATE` и значения `.env` больше не
подменяют эти данные в «О системе». Для Docker без `.git` используйте wrapper из
чистого закоммиченного checkout: он передаёт фактический HEAD отдельным build arg.
Без SHA Docker-сборка завершится ошибкой вместо публикации неизвестных метаданных.

```bash
npm run build
# Из корня репозитория; только сборка, без запуска или развёртывания:
python3 scripts/build_images.py
```

## Проверки

```bash
npm run lint
npm run typecheck
npm test
npm run build
npm run smoke
npm run test:e2e
npm run audit
```

`npm run audit` блокирует любые high/critical findings, кроме явно проверенного advisory React
Router для RSC/server actions: приложение является client-only Vite SPA и этот режим не включает.

Visual screenshots обновляются только явно и используют browser route fixtures, отсутствующие в
production bundle:

```bash
ACKB_UPDATE_SCREENSHOTS=1 npx playwright test e2e/product-ui.spec.ts --grep "captures approved"
```
# Editorial guide

`src/content/editorial-guide.md` is the single canonical card-filling guide.
Edit that Markdown file directly; do not duplicate its content in JSX or public
assets. The authenticated `/editor-guide` route renders it with react-markdown,
GFM tables and prefixed heading anchors (`guide-…`). Raw HTML is disabled.
The card editor opens the guide in a separate tab without leaving the draft.
