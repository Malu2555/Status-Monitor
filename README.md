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

- **Backend:** Django 6 + Django Ninja (auto OpenAPI docs at `/api/docs`)
- **Frontend:** Vue 3 + Vite + vanilla CSS (design tokens + utilities + components)
- **Auth:** JWT — access token held in memory; refresh token in an **httpOnly,
  SameSite=Strict cookie** (`path=/api/auth`), rotated on every refresh with
  reuse detection (blacklist) and a CSRF double-submit check
- **2FA:** opt-in TOTP with single-use recovery codes, managed at `/security`
- **Billing:** Polar.sh subscriptions (merchant of record) — Free (1 monitor,
  5-min checks), Pro ($9/mo, 10 monitors, 1-min), Business ($29/mo, 50
  monitors, 1-min)
- **Monitoring:** `manage.py run_checks` — schedule it every minute via
  cron/Task Scheduler; it checks every monitor whose interval has elapsed and
  evaluates heartbeat monitors against their last inbound ping.
  Each `Check` is stamped with `REGION_NAME`, so several runners (one per
  region) feed the per-region consensus view at `GET /api/monitors/{id}/regions`.
- **TLS expiry:** `manage.py check_ssl` (daily) records each https certificate's
  expiry and queues a warning/critical alert through the notification outbox.
- **Notifications:** email, generic webhook, Slack, Discord and Telegram
  channels, delivered through a retrying outbox (`manage.py deliver_notifications`).
- **Status pages:** branded public pages (`StatusPage` model + `/p/<slug>` in the
  SPA, backed by `GET /api/public/statuspages/<slug>`) showing a chosen subset
  of monitors.
- **Security:** SSRF guard on monitor URLs (public IPs only, redirects
  re-validated per hop), rate limiting (brute-force 5/min, per-IP envelope
  1500/h, public feed 60/min, per-user monitor writes, global cap), security
  headers (CSP, nosniff, frame-deny, referrer), explicit CORS allow-list with
  credentials
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
  accounts/         custom User, JWT issuance, cookie helpers, blacklist
  monitors/         Monitor/Check models, CRUD + public API, check engine,
                    management/commands/run_checks.py (+ self-monitor seed)
  billing/          Polar checkout/portal/webhook, plan limits
frontend/           Vue 3 + Vite SPA
  src/api/          fetch client (silent refresh, CSRF header)
  src/assets/css/   main.css (tokens+reset) · utilities.css (atomic) · components.css
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
  `/enable` (staff JWT only) plus bulk actions in the Django admin. Disabling
  pauses the owner's active monitors and remembers their IDs, so re-enabling
  resumes exactly those and leaves monitors the user paused themselves alone.
- **Policies** — `GET /api/policies/<slug>` returns the current versioned text.
  Edit `Policy` rows in the admin (or add a new version) and bump
  `TOS_VERSION` so new signups stamp the version they accepted.
- **Cron over HTTP** — `GET /api/admin/run` lists the jobs and
  `POST /api/admin/run/{run-checks|deliver-notifications|check-ssl}` runs the
  matching management command. Staff JWT only, throttled at 2/min per user, so
  an external scheduler can drive the minute jobs on a host without a cron
  add-on (`.github/workflows/cron.yml` is the ready-made template).

## Tests

```powershell
cd backend
.venv\Scripts\python manage.py test     # auth + 2FA + recovery codes, ToS consent,
                                        # moderation disable/enable, honeypot + IP blocking,
                                        # cron-over-HTTP triggers, CSRF, refresh rotation,
                                        # SSRF, plan limits, Polar webhook signature/idempotency,
                                        # check engine, TLS state, multi-region, status pages
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
- Polar webhooks are idempotent (see the `WebhookEvent` ledger in the
  Django admin). Downtime alerts flow through an outbox: schedule
  `manage.py deliver_notifications` every minute next to `run_checks`, and
  manage channels via the admin. Security/billing actions land in the
  read-only `AuditLogEntry` admin view.
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

## Shipping it (no domain required)

Free-tier path that stays at **$0/month** until you have paying users:

| Layer | Service | Notes |
|---|---|---|
| SPA | **Vercel** (`*.vercel.app`) | free HTTPS + auto-deploy on `git push` |
| API + cron | **Render** Web Service | free tier sleeps after ~15 min idle |
| Postgres | **Neon** free tier | set `DATABASE_URL=postgres://…?sslmode=require` |

- No custom domain is needed to launch — `https://<project>.vercel.app` is a real
  public hostname with a valid certificate; add a domain later in Vercel.
- Free tiers sleep when idle. Point a free pinger (e.g. UptimeRobot, 5-minute
  interval) at `/api/health` so the first dashboard request after a quiet spell
  is warm; `/api/health` is also the correct probe for load balancers.
- **`SELF_MONITOR_URL` points at your own front door**, never at a third-party
  uptime service: if it watched UptimeRobot, the self-monitor would stay green
  while your app was down — exactly the outage you care about.
- Prefer one origin: let Vercel rewrite `/api/*` to the API host. If you split
  origins instead, set `CORS_ALLOWED_ORIGINS=https://<project>.vercel.app`
  (DEBUG automatically adds the Vite dev origins) and `COOKIE_SECURE=True`.
- **Cron on a host without a cron add-on** (Render free): enable
  `.github/workflows/cron.yml` and set the `API_BASE_URL` + `CRON_JWT`
  repository secrets. It calls the staff-only `/api/admin/run/*` endpoints every
  minute (`run_checks`, `deliver_notifications`) and daily (`check_ssl`).
  On a box with cron/Task Scheduler, use `scripts/crontab.example` or
  `scripts/run_checks_scheduled.ps1` instead — same three commands.
- Abuse controls are on by default: 256 KB body cap, registration honeypot
  (`company` field), and automatic 24-hour IP blocks after 50 auth failures in
  an hour. Review and lift blocks in the Django admin (*Blocked IPs*), and watch
  *Abuse events* to spot attack patterns.
- Before opening signups: replace the `statusmonitor.example` contact addresses
  in the seeded policies, then set `TOS_VERSION` to the version you published.
