# Architecture

Status Monitor is a Django 6 + Django Ninja API with a Vue 3 SPA. It is a
modular monolith: one deployable unit, domain-oriented Django apps, and a
background loop inside the same container.

## 1. Runtime topology

```
                         ┌──────────────────────────── Render container ─┐
Browser ── HTTPS ──▶ Vercel SPA ──/api/*──▶ gunicorn (2 workers × 4 threads)
                         │                      │            │
                         │                      │            └─ run_scheduler (1 process)
                         │                      ▼
                         │               Django (ninja API, admin, health)
                         │                      │
                         │                      ▼
                         │               Supabase Postgres (pooler)
                         │                  ├─ data
                         │                  └─ django_cache (DatabaseCache)
                         └─ static assets
```

- **Web process:** gunicorn serves the API; Django middleware applies security
  headers, IP blocks, admin gating, sessions, auth, OTP and CSRF.
- **Scheduler process:** `manage.py run_scheduler` runs minute jobs
  (`run_checks`, `deliver_notifications`), daily jobs (`check_ssl`,
  `check_domains`, `crawl_links`, `prune_history`) and is intentionally a
  separate process from gunicorn.
- **Single-replica assumption:** the scheduler has no distributed lock. Run at
  most one scheduler per database unless you add an advisory lock.
- **Free-tier shape:** Render sleeps when idle, which pauses the scheduler;
  UptimeRobot pings `/api/health` to wake it. See `DEPLOYMENT.md`.

## 2. Request lifecycle

```
Request
  → SecurityMiddleware / CORS
  → SecurityHeadersMiddleware        (CSP, nosniff, frame-deny, permissions-policy)
  → BlockedIPMiddleware             (403 before routing)
  → AdminGuardMiddleware            (404/429 for /admin/* when enabled)
  → Session / Common / CSRF / Auth
  → OTPMiddleware                    (request.user gains is_verified)
  → ninja API
       auth handler (Bearer JWT or X-API-Key)
       throttle classes (global envelope + route scopes)
       view → services → ORM
  → response (throttle headers, cache headers, audit already written)
```

- API views are **CSRF-exempt** by design; state-changing routes use the
  `Authorization` header. The only cookie-authenticated write is
  `POST /api/auth/refresh`, protected by a double-submit CSRF check with
  `secrets.compare_digest`.
- IP addresses for throttles, audit and auto-block all go through
  `accounts.abuse.client_ip`, which honours `TRUSTED_PROXY_IPS` and
  `PROXY_HOPS`.

## 3. Backend layering

```
config/        settings, URLconf, ninja root, middleware, throttles, app config
core/          shared kernel: outbound network safety (SSRF guard / HTTP)
accounts/      User, JWT, cookies, 2FA, abuse, admin hardening, moderation
monitors/      Monitor/Check/Incident models, check engine, public feed, stats
notifications/ channels + transactional outbox (NotificationDelivery)
billing/       Polar checkout/portal/webhook, plan limits
audit/         append-only AuditLogEntry + helper
health/        unauthenticated liveness probe
```

Rules of thumb:

- Routers (`*/api.py`) parse/validate input, enforce ownership, call services,
  and serialize. They should not contain check logic, pricing rules, or
  multi-step business transactions.
- `*/services.py` is the use-case layer; it is where retries, state
  transitions and external I/O live. It is directly testable without HTTP.
- Models are persistence + invariants. Cross-app imports go through services,
  not models, wherever possible.
- Outbound HTTP goes through `core.net` (SSRF guard, timeouts, no automatic
  redirects) rather than calling `httpx` directly.

## 4. Core domain model

| Aggregate | Key tables | Notes |
|---|---|---|
| Account | `accounts_user`, `ApiToken`, `RevokedRefreshToken`, `RecoveryCode` | email unique; soft-disable via `is_active` + `disabled_reason` |
| Monitor | `monitors_monitor`, `monitors_check`, `Incident`, `MaintenanceWindow` | `Check` is append-heavy and indexed by `(monitor, -checked_at)` |
| Notification | `MonitorNotificationChannel`, `NotificationDelivery` | outbox row per event × channel, retries → dead |
| Billing | `Subscription`, `WebhookEvent` | provider state mirrored locally; webhook idempotency ledger |
| Governance | `AuditLogEntry`, `AbuseEvent`, `BlockedIP`, `Policy` | append-only evidence trail |

Growth: `Check`, `AbuseEvent`, `AuditLogEntry` and delivered outbox rows grow
with traffic. `manage.py prune_history` (scheduled daily) is the retention
control; see `RUNBOOK.md`.

## 5. Patterns in use

- **Transactional outbox:** alert events are written in the same transaction as
  the check, then delivered by `deliver_notifications` with backoff/retry. This
  decouples probe latency from provider latency.
- **Ports and adapters (pragmatic):** Polar is reached through
  `billing/services.py`; outbound HTTP through `core/net.py`; transports through
  `notifications/channels.py`. Swapping a provider should touch one adapter.
- **Functional core, imperative shell:** URL validation, uptime math and
  schedule decisions are pure helpers; the shell handles I/O and persistence.
- **CQRS-lite:** read models (`uptime_stats`, `bulk_uptime`) compute aggregates
  at read time. If the dashboard gets hot, materialize daily rollups alongside
  `prune_history`.
- **Idempotency:** Polar deliveries are keyed by `Webhook-Id`; refresh rotation
  burns the presented token before issuing a new pair.
- **Explicit configuration over convention:** everything deployment-specific is
  an env var, documented in `DEPLOYMENT.md` and `render.env.example`.

## 6. Frontend

- `src/api/client.js`: in-memory access token, one silent refresh + retry,
  `credentials: 'same-origin'`, CSRF header on refresh, friendly 429/503 text.
- Relative `/api/*` URLs work in dev (Vite proxy) and production (Vercel
  rewrite), keeping cookies first-party.
- `useTheme` applies `<html data-theme>` before first paint; CSS custom
  properties are the single color source of truth.
- Views are route-level code-split; Pinia stores own session and dashboard
  state.

## 7. Extension points

| Need | Where to add |
|---|---|
| New monitor kind | `monitors/services.py` + `monitors/models.py` `Kind` + schema choices + tests |
| New notification channel | `notifications/channels.py` handler + kind choice + validation |
| New billing plan | `billing/services.py` plan table + `POLAR_PRODUCT_*` env + UI copy |
| New admin action | `accounts/management/commands/` or a Django admin action |
| New scheduled job | `monitors/management/commands/` + `run_scheduler` daily slots + `admin_api.JOB_COMMANDS` |
| Shared HTTP/security helper | `backend/core/` (never import from `monitors` into `notifications`) |

## 8. Known technical debt

1. Notification channel addresses are stored in plaintext (see `SECURITY.md`);
   encryption needs a design compatible with the uniqueness constraint.
2. Trusted-proxy hop count is configuration, not auto-detected; verify after any
   topology change.
3. `monitors/api.py` is large — split into read/write routers when it next
   changes.
4. No frontend unit tests yet; the mobile audit is a browser script.
5. OpenAPI docs are disabled in production; regenerate the local schema with
   `manage.py export_openapi` before `npm run api:gen` (a CI drift check is on
   the backlog).

See `docs/ADRs/` for the decisions behind these trade-offs.

