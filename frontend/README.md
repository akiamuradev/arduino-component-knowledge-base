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
- тема хранит только пользовательское предпочтение `ackb-theme`; права и auth state туда не
  записываются; внешний blocking script применяет тему до старта React;
- оформление выбирается одной доступной кнопкой с меню, единым набором SVG-иконок и вариантами
  «Светлое», «Тёмное», «Как на устройстве»; меню поддерживает клавиатурную навигацию;
- `/about` показывает автора `akiamuradev`, фактическую PolyForm Noncommercial License,
  репозиторий и build info;
- login OLED собран из HTML/CSS/SVG, использует один `requestAnimationFrame`, CSS variables,
  reduced-motion и не участвует в проверке credentials или roles;
- global search передаёт `q` в реальный catalog endpoint через URL.
- шапка показывает серверное имя и русское название роли, а ссылки фильтруются только по
  permissions из `/auth/me`; на мобильном экране основная навигация остаётся доступной;
- редакционная навигация разделяет работу с материалами и административные инструменты.

Public catalog API пока не отдаёт связанные media/download URL и provenance. Frontend содержит
optional typed contracts `CatalogMedia`, `SourceAttribution` и `ContentProvenance`, но не создаёт
фиктивные production-данные. `MediaGallery` и `SourceAttributionBlock` появляются только при
наличии metadata. `/sources` намеренно не создан до появления агрегирующего backend endpoint.

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

Все mutations включают CSRF; update/publish/archive передают optimistic `revision`.
`revision_conflict` не ретраится и не перезаписывает локальную форму. Пока FastAPI не
реализует эти endpoints, dashboard/editor показывают явное состояние ошибки.

Маршрут `/admin/jobs` дополнительно защищён administrator UX guard и ожидает
`GET /api/v1/admin/jobs` и CSRF-protected `POST /api/v1/admin/jobs/{id}/retry`. Backend RBAC
остаётся обязательной границей; список обновляется каждые пять секунд и не подменяется mock data.

## Локальный запуск

```bash
npm ci
npm run dev
```

Vite проксирует `/api` на `http://127.0.0.1:8000`. Production должен публиковать frontend и
backend через один reverse proxy origin. `VITE_API_BASE_URL`, если задан, обязан быть
same-origin абсолютным path, например `/api/v1`; URL внешнего origin отклоняется при старте.

Build metadata необязательны и не должны содержать секреты:

```bash
VITE_APP_VERSION=1.0.0 VITE_COMMIT_SHA=<commit> VITE_BUILD_DATE=<ISO-8601> npm run build
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
