# 📡 Status Monitor

A website status monitor with a **free public status page** (anyone can check the
health of all monitored sites) and a **private, authenticated dashboard** where
users register, log in with JWT + httpOnly cookies, add their own sites, and pay
via Polar.sh subscriptions (a merchant of record, so global tax/VAT is handled
for us).

Status Monitor is an open-source uptime and status-page platform with
subscription billing, a compliance-ready audit log, and a Django + PostgreSQL
data model you own and can query. It is not an UptimeRobot replacement — it is
the option for when you want the same uptime coverage *and* the receipts.

Released under the **MIT licence** — see `LICENSE`.

- **Backend:** Django 6 + Django Ninja (OpenAPI schema generated in dev)
- **Frontend:** Vue 3 + Vite + vanilla CSS (design tokens + utilities + components)
- **Auth:** JWT — access token held in memory; refresh token in an **httpOnly,
  SameSite=Strict cookie** (`path=/api/auth`), rotated on every refresh with
  reuse detection (blacklist) and a CSRF double-submit check
- **2FA:** opt-in TOTP with single-use recovery codes, managed at `/security`
- **Billing:** Polar.sh subscriptions (merchant of record) — Free (1 monitor,
  5-min checks), Pro ($9/mo, 10 monitors, 1-min), Business ($29/mo, 50
  monitors, 1-min)
- **Monitoring:** `manage.py run_scheduler` (container) or `manage.py run_checks`
  (cron/Task Scheduler). It checks every monitor whose interval has elapsed and
  evaluates heartbeat monitors against their last inbound ping. The container
  loop also runs `deliver_notifications` every minute and the daily sweeps.
  Each `Check` is stamped with `REGION_NAME`, so several runners (one per
  region) feed the per-region consensus view at `GET /api/monitors/{id}/regions`.
- **TLS expiry:** `manage.py check_ssl` (daily) records each https certificate's
  expiry and queues a warning/critical alert through the notification outbox.
- **Keyword/content monitoring:** `kind="keyword"` asserts that a page contains
  (or does not contain) a phrase, catching "HTTP 200 but broken" pages.
- **Domain expiry:** `kind="domain"` reads the registrar expiry via RDAP in
  `manage.py check_domains` (daily); warns at 30 days and escalates at 7.
- **Broken links:** `kind="broken_links"` crawls same-site links (robots.txt
  respected, SSRF-guarded) in `manage.py crawl_links` (daily) and alerts on new
  dead links. Returns HTTP 4xx/5xx, and the dashboard lists every open one.
- **Notifications:** email, generic webhook, Slack, Discord and Telegram
  channels, delivered through a retrying outbox (`manage.py deliver_notifications`).
- **Status pages:** branded public pages (`StatusPage` model + `/p/<slug>` in the
  SPA, backed by `GET /api/public/statuspages/<slug>`) showing a chosen subset
  of monitors.
- **Marketing site:** the SPA root (`/`) is a landing page (hero URL capture,
  product preview, features, use cases, pricing); the live public feed lives at
  `/status`, and the visitor CTA carries the entered URL through registration
  into the monitor form.
- **Light/dark theme:** system-preference by default with a manual
  System → Light → Dark toggle in the navbar. One `<html data-theme>` switch
  flips the CSS token set; the preference is stored in `localStorage`, applied
  before first paint (no flash), and Chart.js re-reads the palette on change.
- **Mobile:** 390px-audited layouts (no horizontal scroll), 44px touch targets,
  safe-area insets, iOS-zoom-safe inputs, hamburger menu with Escape/outside-tap
  closing + scroll lock, and a sticky landing CTA on small screens.
- **Security:** SSRF guard on monitor URLs (public IPs only, redirects
  re-validated per hop), rate limiting (brute-force 5/min, per-IP envelope
  1500/h, public feed 60/min, per-user monitor writes, global cap), security
  headers (CSP, nosniff, frame-deny, referrer, permissions-policy), explicit
  CORS allow-list with credentials, and an opt-in Django admin that requires a
  superuser + TOTP, with lockout and optional IP allow-listing.
- **DoS guard:** application-layer — 256 KB body cap, honeypot field on
  registration, `BlockedIP` table (manual + automatic after 50 auth failures
  from one IP in an hour) enforced by middleware before routing, and
  `X-Forwarded-For` trusted only from `TRUSTED_PROXY_IPS`
- **Legal & moderation:** versioned Terms of Service / Privacy Policy served at
  `/api/policies/<slug>` and rendered at `/terms` + `/privacy`; registration
  stores proof of consent (`tos_accepted_at`, `tos_version`,
  `age_confirmed_at`). Staff can disable an account with a reason — that cuts
  off both JWTs and API keys, pauses its monitors, and lands in the audit log.

## Folder layout

```
backend/            Django project (config/ = settings+api+middleware)
  accounts/         custom User, JWT issuance, cookie helpers, blacklist, admin hardening
  monitors/         Monitor/Check models, CRUD + public API, check engine,
                    management/commands/ (run_checks, run_scheduler, check_ssl,
                    check_domains, crawl_links)
  billing/          Polar checkout/portal/webhook, plan limits
frontend/           Vue 3 + Vite SPA
  src/api/          fetch client (silent refresh, CSRF header)
  src/composables/  useTheme (system/light/dark, persisted, no-FLASH boot)
  src/assets/css/   main.css (tokens+reset) · utilities.css (atomic) · components.css · landing.css
  scripts/          gen-api.mjs · mobile-audit.mjs (CDP overflow + tap-target check)
  vercel.json       SPA fallback + /api proxy to Render
Dockerfile          API + in-container scheduler image (Render)
render.yaml         Render blueprint (Docker, free plan, health check, env)
scripts/            Windows Task Scheduler registration + Linux crontab example
```

## Setup (Windows / dev)

```powershell
# 1. Backend
cd backend
python -m venv .venv  (or reuse the existing .venv)
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env   # then edit .env (SECRET_KEY, Polar keys…)
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py runserver 127.0.0.1:8000

# 2. Frontend (new terminal)
cd frontend
npm install
npm run dev          # http://localhost:5173  (proxies /api → :8000)

# Mobile audit (requires Chrome with --remote-debugging-port=9333 and `npm run dev`)
npm run audit:mobile

# 3. Monitoring every minute (remember the self-monitor 😄)
powershell -ExecutionPolicy Bypass -File ..\scripts\run_checks_scheduled.ps1
# or just run manually anytime:  .venv\Scripts\python manage.py run_checks
```

## Polar (test mode)

```bash
# set in backend/.env
POLAR_ACCESS_TOKEN=polar_oat_...
POLAR_WEBHOOK_SECRET=whsec_...
POLAR_PRODUCT_PRO=prod_xxx
POLAR_PRODUCT_BUSINESS=prod_xxx
POLAR_USE_SANDBOX=True      # sandbox during dev; False in production

# create the two subscription products in the Polar dashboard, add a webhook
# pointing at /api/billing/webhook (Standard Webhooks signing), then expose
# your local server (e.g. `ngrok http 8000`) so Polar can reach it.
```

Polar is a merchant of record: it collects payment, handles global tax/VAT,
and pays you net. After a successful checkout its
`subscription.created`/`subscription.active` webhook activates the plan → the
monitor limit and minimum check interval update immediately.

## API & integrations

- **API tokens** — create one on the `/security` page (or `POST /api/auth/tokens`);
  send it as the `X-API-Key` header on any `/api/monitors` request. `read`
  tokens can view but not mutate.
- **2FA recovery codes** — 10 single-use codes are issued when TOTP is enabled;
  regenerate them from `/security` with a current TOTP code. Either a TOTP code
  or a recovery code satisfies the login challenge.
- **Heartbeat monitors** — create with `{"kind": "heartbeat"}`; the response
  includes `heartbeat_token`. Ping `POST /api/public/heartbeat/<token>` from
  your cron job; if no ping arrives within
  `check_interval_seconds + heartbeat_grace_seconds`, the monitor goes down and
  alerts fire through the normal channels.
- **Embeddable badge** — `GET /api/public/badge/<monitor_id>.svg` (SVG, 60s cache).
- **Compliance export** — `GET /api/monitors/export.csv?hours=720` returns a
  per-monitor uptime/incident CSV suitable for SOC2/ISO evidence.
- **Postmortems** — `POST /api/monitors/<id>/incidents/<incident_id>/postmortem`
  generates a customer-facing draft from the incident timeline (surfaced on the
  public status feed).
- **Status pages** — full owner-scoped CRUD at `/api/statuspages`, an in-app
  manager at `/status-pages`, public page at `/p/<slug>`, public data at
  `/api/public/statuspages/<slug>`.
- **Account moderation** — `POST /api/auth/moderation/users/<id>/disable` and
  `/enable` (staff JWT only) plus routine `manage.py moderate …` commands
  (`disable_user`, `enable_user`, `block_ip`, `unblock_ip`, `list_recent`).
  The Django admin is opt-in (`ADMIN_ENABLED`) and superuser + TOTP only.
  Disabling pauses the owner's active monitors and remembers their IDs, so
  re-enabling resumes exactly those and leaves monitors the user paused
  themselves alone.
- **Policies** — `GET /api/policies/<slug>` returns the current versioned text.
  Edit `Policy` rows in the admin (or add a new version) and bump
  `TOS_VERSION` so new signups stamp the version they accepted.
- **Cron over HTTP** — `GET /api/admin/run` lists the jobs and
  `POST /api/admin/run/{run-checks|deliver-notifications|check-ssl|check-domains|crawl-links}`
  runs the matching management command (superuser JWT). For machine callers use
  `POST /api/admin/scheduler/{job}` with the `X-Scheduler-Token` header
  (`SCHEDULER_TOKEN` env); the production container calls the commands directly
  and doesn't need either endpoint.
- **Account self-service** — change password (invalidates every other session),
  change email (confirmed by a link sent to the *new* address), sign out all
  other sessions, and delete your own account (PII anonymised, monitors paused).
- **Notification channels UI** — users add/pause/delete their own email,
  webhook, Slack, Discord and Telegram channels at `/notifications`, with a
  **Test** button that dispatches a synthetic message.
- **Maintenance windows UI** — schedule planned downtime at `/maintenance`;
  checks that fail inside the window do not open incidents or alert.
- **Incident history UI** — the dashboard detail panel lists past incidents
  (duration, failed checks, last HTTP code) with the generated postmortem.

## Tests

```powershell
cd backend
.venv\Scripts\python manage.py test     # auth + 2FA + recovery codes, ToS consent,
                                        # account self-service (password/email/sessions/delete),
                                        # notification channels UI, maintenance windows,
                                        # incident history, moderation disable/enable,
                                        # honeypot + IP blocking, cron-over-HTTP triggers,
                                        # scheduler token + admin login lockout,
                                        # CSRF, refresh rotation, SSRF, plan limits,
                                        # Polar webhook signature/idempotency, check engine,
                                        # TLS state, multi-region, status pages
```

## Production notes

- Set `DEBUG=False`, `ALLOWED_HOSTS`, `COOKIE_SECURE=True` and
  `SECURE_SSL_REDIRECT=True` in `.env` behind HTTPS (HSTS etc. enabled
  automatically), serve the built `frontend/dist` from the same origin.
- Set `DATABASE_URL` (PostgreSQL DSN, e.g.
  `postgres://user:password@host:5432/statusmonitor`) to switch from the dev
  SQLite + LocMemCache to PostgreSQL + a database-backed cache. On first
  deploy run `.venv\Scripts\python manage.py migrate` **and**
  `.venv\Scripts\python manage.py createcachetable` — rate-limit buckets
  then stay global across all workers/instances.
- To move the cache to Redis later: `pip install redis`, run a Redis server,
  and switch `CACHES["default"]["BACKEND"]` to
  `django.core.cache.backends.redis.RedisCache` (with a redis:// `LOCATION`).
  Everything using the cache (throttling) keeps working — no code changes.
- `GET /api/health` is an unauthenticated liveness probe (DB + cache) for
  load balancers / k8s — 200 with a JSON body when healthy, 503 otherwise.
  It also keeps the free Render instance (and the scheduler inside it) awake.
- Polar webhooks are idempotent (see the `WebhookEvent` ledger in the Django
  admin, when enabled). Downtime alerts flow through an outbox:
  `manage.py run_scheduler` calls `deliver_notifications` every minute next to
  `run_checks` (or schedule both with cron), and channels are managed in the
  SPA. Security/billing actions land in the read-only `AuditLogEntry` admin
  view.
- Check intervals are minute-granular by design (cron). Sub-minute checks
  would need a persistent worker (Celery/Django-Q2) — the check logic in
  `monitors/services.run_check` is already worker-ready.
- **Multi-region**: deploy the same image in each region with a distinct
  `REGION_NAME` (e.g. `us-east`, `eu-west`, `ap-south`) while pointing at the
  same PostgreSQL. Each runner writes `Check` rows tagged with its region, and
  the dashboard's *Regions (consensus)* view compares them.
- **TLS expiry**: schedule `manage.py check_ssl` daily (see
  `scripts/crontab.example` / `scripts/run_checks_scheduled.ps1`). It only
  queues alerts when a certificate crosses `SSL_WARN_DAYS` or
  `SSL_CRITICAL_DAYS`, so there is no repeat spam.
- **Custom status pages**: manage them in-app at `/status-pages` (or the Django
  admin) — choose title, slug, theme color, visibility, and the monitors to
  publish. They render publicly at `/p/<slug>`.

## Deployment

Free-tier topology: **Vercel** (SPA) + **Render** (Docker API + in-container scheduler) + **Supabase** (Postgres pooler), with Polar sandbox billing and UptimeRobot pings.

- Full runbook: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- Environment template: [`render.env.example`](render.env.example) (placeholders only; real values live in Render)
- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) - Security: [`docs/SECURITY.md`](docs/SECURITY.md) - Runbook: [`docs/RUNBOOK.md`](docs/RUNBOOK.md)

Keep `ADMIN_ENABLED=False` in production; use `manage.py moderate ...` for routine work and enable the admin only for break-glass sessions.

`GET /api/health` is the Render health check and the UptimeRobot wake ping. Free Render instances sleep after ~15 min idle, which also pauses the scheduler - upgrade when you depend on minute-level checks.