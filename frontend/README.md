# Frontend

React + strict TypeScript приложение на Vite. Оно обращается только к same-origin `/api/v1`,
использует opaque cookies backend и не хранит session tokens или роли в localStorage.

## Структура

- `src/api` — типизированные HTTP contracts, общий client, CSRF и typed errors;
- `src/auth` — TanStack Query для backend-resolved principal;
- `src/routing` — authentication/role UX guards; они не являются security boundary;
- `src/layouts` — student и administrator shells;
- `src/pages` — route-level страницы;
- `src/workspace` — queries для dashboard, карточек и категорий;
- `src/jobs` — administrator-only polling и retry mutations для durable job monitor;
- `src/components` — общие loading/error states.

## Editorial workspace contract

Маршруты `/admin`, `/admin/components`, `/admin/components/new` и
`/admin/components/:id/edit` доступны teacher/administrator как UX. Frontend ожидает:

- `GET /api/v1/workspace/components`;
- `GET /api/v1/workspace/categories`;
- `GET|PUT /api/v1/workspace/components/{id}`;
- `POST /api/v1/workspace/components`;
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

## Проверки

```bash
npm run lint
npm run typecheck
npm test
npm run build
npm run smoke
npm audit --audit-level=high
```
