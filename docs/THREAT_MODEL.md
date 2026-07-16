# Модель угроз

## Scope и активы

Модель охватывает browser, reverse proxy, FastAPI, Dramatiq workers, PostgreSQL, Redis,
MinIO и исходящие запросы parser к трём утверждённым сайтам. Защищаются credentials и
sessions, роли, draft/teacher-only материалы, published catalog, provenance, media binary,
job state и audit. Backup, корпоративный TLS termination и host firewall остаются deployment
ответственностью и не подменяются application controls.

## Границы доверия

```text
untrusted browser -> reverse proxy -> backend authorization -> internal data network
untrusted URL/HTML -> parser worker -> exact allowlist + pinned HTTPS -> draft only
untrusted binary -> private quarantine -> media worker without egress -> safe variants
```

Только reverse proxy публикует host port. `edge` и `data` являются internal Compose networks.
PostgreSQL, Redis, MinIO, backend и media worker не имеют внешнего egress. Отдельный
`parser-worker` подключён к `parser-egress`, но его URL policy разрешает только HTTPS exact
hosts, проверяет все DNS answers и каждый redirect.

## Угрозы, controls и доказательства

| Угроза | Control | Проверка |
|---|---|---|
| Повышение роли или IDOR | backend default-deny RBAC; ownership/object visibility; чужой object возвращается как not found | route-role matrix, media/import foreign-ID tests |
| CSRF и cross-origin API | session `SameSite=Strict`; session-bound double-submit CSRF; exact same-origin middleware; permissive CORS отсутствует | mutation dependency audit, Origin/preflight tests |
| XSS/clickjacking | React text rendering; raw HTML запрещён; CSP, `nosniff`, `frame-ancestors 'none'`, `X-Frame-Options: DENY` | response/proxy header tests |
| Parser SSRF | HTTPS exact allowlist; no userinfo/custom port; all-address validation; IP pinning with Host/SNI; redirect revalidation; proxy/cookies disabled; decoded-body/header/time limits | URL, mixed DNS, redirect, gzip/body/header adversarial tests |
| Malicious upload | private quarantine; server key; declared/actual size; magic/container/decode/dimension/frame checks; metadata-free re-encode; bounded FFmpeg without shell and with `file,pipe` protocol allowlist | polyglot/trailing-data, MIME, animation, dimension, video command tests |
| Media processor lateral movement | media worker подключён только к internal `data`; parser egress находится в отдельном worker | Compose network contract test |
| Draft/teacher data disclosure | published snapshots and search allowlist; teacher examples filtered before response | catalog/search regression tests |

## Остаточные риски и assumptions

- Compose network policy ограничивает egress контейнера, но CPU/memory/process limits и host
  firewall должны быть проверены в целевом Linux deployment.
- CSP рассчитан на production bundle со скриптами и стилями same-origin; opt-in Swagger UI
  не является production UI и может потребовать отдельной административной policy.
- Права на перенос материалов трёх источников не подтверждены, поэтому parser сохраняет только
  `metadata_only` draft.
- Реальные penetration test, dependency/container vulnerability scan и restore drill входят в
  этап стабилизации перед релизом.
