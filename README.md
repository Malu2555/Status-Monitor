# 📡 Status Monitor

A website status monitor with a **free public status page** (anyone can check the
health of all monitored sites) and a **private, authenticated dashboard** where
users register, log in with JWT + httpOnly cookies, add their own sites, and pay
via Stripe subscriptions.

- **Backend:** Django 6 + Django Ninja (auto OpenAPI docs at `/api/docs`)
- **Frontend:** Vue 3 + Vite + vanilla CSS (design tokens + utilities + components)
- **Auth:** JWT — access token held in memory; refresh token in an **httpOnly,
  SameSite=Strict cookie** (`path=/api/auth`), rotated on every refresh with
  reuse detection (blacklist) and a CSRF double-submit check
- **Billing:** Stripe subscriptions — Free (1 monitor, 5-min checks), Pro
  ($9/mo, 10 monitors, 1-min), Business ($29/mo, 50 monitors, 1-min)
- **Monitoring:** `manage.py run_checks` — schedule it every minute via
  cron/Task Scheduler; it checks every monitor whose interval has elapsed
- **Security:** SSRF guard on monitor URLs (public IPs only, redirects
  re-validated per hop), rate limiting (brute-force 5/min, public feed 60/min,
  per-user monitor writes, global cap), security headers (CSP, nosniff,
  frame-deny, referrer), explicit CORS allow-list with credentials

## Folder layout

```
backend/            Django project (config/ = settings+api+middleware)
  accounts/         custom User, JWT issuance, cookie helpers, blacklist
  monitors/         Monitor/Check models, CRUD + public API, check engine,
                    management/commands/run_checks.py (+ self-monitor seed)
  billing/          Stripe checkout/portal/webhook, plan limits
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
Copy-Item .env.example .env   # then edit .env (SECRET_KEY, Stripe keys…)
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

## Stripe (test mode)

```bash
# set in backend/.env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO=price_xxx
STRIPE_PRICE_BUSINESS=price_xxx

# create the two prices in the Stripe dashboard (monthly subscriptions),
# then forward webhooks to the local server:
stripe listen --forward-to localhost:8000/api/billing/webhook
```

Test card: `4242 4242 4242 4242` (any future expiry, any CVC). After a
successful checkout the Stripe webhook activates the plan → the monitor limit
and minimum check interval update immediately.

## Tests

```powershell
cd backend
.venv\Scripts\python manage.py test     # 19 tests: auth flow, CSRF, refresh rotation,
                                        # SSRF, plan limits, public feed, check engine
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
- Stripe webhooks are idempotent (see the `StripeEvent` ledger in the
  Django admin). Downtime alerts flow through an outbox: schedule
  `manage.py deliver_notifications` every minute next to `run_checks`, and
  manage channels via the admin. Security/billing actions land in the
  read-only `AuditLogEntry` admin view.
- Check intervals are minute-granular by design (cron). Sub-minute checks
  would need a persistent worker (Celery/Django-Q2) — the check logic in
  `monitors/services.run_check` is already worker-ready.
