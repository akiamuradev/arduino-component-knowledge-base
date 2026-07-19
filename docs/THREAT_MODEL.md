# Модель угроз

## Scope и активы

Модель охватывает browser, reverse proxy, FastAPI, Dramatiq workers, PostgreSQL, Redis,
MinIO, исторический HTML boundary и зарегистрированные Git repository snapshots. Защищаются credentials и
sessions, роли, draft/teacher-only материалы, published catalog, provenance, media binary,
job state и audit. Backup, корпоративный TLS termination и host firewall остаются deployment
ответственностью и не подменяются application controls.

## Границы доверия

```text
untrusted browser -> reverse proxy -> backend authorization -> internal data network
registered repository snapshot -> exact repository + immutable commit -> draft only
untrusted binary -> private quarantine -> media worker without egress -> safe variants
```

Только reverse proxy публикует host port и подключён к host-facing сети `ingress`.
`edge` и `data` являются internal Compose networks.
PostgreSQL, Redis, MinIO, backend и media worker не имеют внешнего egress. Отдельный
`parser-worker` подключён к `parser-egress`, но его URL policy разрешает только HTTPS exact
hosts, проверяет все DNS answers и каждый redirect.

## Угрозы, controls и доказательства

| Угроза | Control | Проверка |
|---|---|---|
| Повышение роли или IDOR | backend default-deny RBAC; ownership/object visibility; чужой object возвращается как not found | route-role matrix, media/import foreign-ID tests |
| CSRF и cross-origin API | session `SameSite=Strict`; session-bound double-submit CSRF; exact same-origin middleware; permissive CORS отсутствует | mutation dependency audit, Origin/preflight tests |
| XSS/clickjacking | React text rendering; raw HTML запрещён; CSP, `nosniff`, `frame-ancestors 'none'`, `X-Frame-Options: DENY` | response/proxy header tests |
| Parser SSRF | inactive website policy before fetch; repository URL is registered, never user supplied; VM acquisition retains HTTPS/DNS/size limits | source-policy, repository identity and acquisition validation tests |
| Malicious Git content | full commit, bounded path/file snapshot, no hooks/submodules/builds, MDX non-execution, bounded S-expression reader | fixtures with JSX, code, traversal, broken frontmatter/S-expression and unknown types |
| Malicious upload | private quarantine; server key; declared/actual size; magic/container/decode/dimension/frame checks; metadata-free re-encode; bounded FFmpeg without shell and with `file,pipe` protocol allowlist | polyglot/trailing-data, MIME, animation, dimension, video command tests |
| Media processor lateral movement | media worker подключён только к internal `data`; parser egress находится в отдельном worker | Compose network contract test |
| Draft/teacher data disclosure | published snapshots and search allowlist; teacher examples filtered before response | catalog/search regression tests |

## Остаточные риски и assumptions

- Compose network policy ограничивает egress контейнера, но CPU/memory/process limits и host
  firewall должны быть проверены в целевом Linux deployment.
- CSP рассчитан на production bundle со скриптами и стилями same-origin; opt-in Swagger UI
  не является production UI и может потребовать отдельной административной policy.
- Старые website sources деактивированы; AlexGyver explicitly denied. Seeed/KiCad imports
  сохраняют собственные license snapshots и остаются draft до ручной проверки.
- Реальные penetration test, dependency/container vulnerability scan и restore drill входят в
  этап стабилизации перед релизом.
