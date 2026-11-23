# Deployment runbook — Vercel + Render + Supabase

Production topology:

```
Browser
  │  https://your-app.vercel.app
  ▼
Vercel (static SPA) ──rewrite /api/*──▶ Render (Docker: gunicorn + run_scheduler)
                                            │
                                            ▼
                                     Supabase Postgres (pooler, sslmode=require)
```

- **Frontend:** Vercel, Root Directory = `frontend`
- **API + scheduler:** one Render Docker web service (free plan sleeps when idle)
- **Database:** Supabase free Postgres via the pooler
- **Billing:** Polar (start in sandbox)
- **Wake/uptime:** UptimeRobot every 5 minutes on `/api/health`
- One-off values: copy `render.env.example` → fill in Render's dashboard. **Never commit real values.**

## 0. Before you deploy

- `DEBUG=False`, `SECRET_KEY` and `JWT_SIGNING_KEY` are independent random values.
- `render.yaml` is the Render blueprint; `frontend/vercel.json` is the Vercel config.
- The container start command runs `migrate` + `createcachetable`, starts
  `manage.py run_scheduler` in the background, then execs gunicorn.
- Keep `ADMIN_ENABLED=False` until you need the break-glass admin.

### Where the image is built

- **Render** builds the deployment image in its cloud pipeline from the pushed
  commit (`runtime: docker`, `dockerfilePath: ./Dockerfile`, `dockerContext: .`).
  Nothing needs to be built locally for a deploy.
- **CI** independently builds the same image and smoke-tests it
  (`GET /api/health`), so a broken Dockerfile or start command fails the pull
  request instead of the Render deploy.
- Dockerfile knobs are deliberately few: base Python tag, `PORT`, and the
  gunicorn CMD line. Runtime settings (plan, env vars, health check) live in
  `render.yaml`; switching Render to its native Python runtime is a service
  setting, not a Dockerfile edit.


## 1. Database (Supabase)

1. Create a project and copy the **pooler** connection string (IPv6-safe):

   ```env
   DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
   ```

2. Keep `?sslmode=require`; `settings.py` only applies SSL when present.
3. Transaction mode (6543) is fine for this workload. If long-lived workers log
   connection errors, use session mode on port **5432** of the same pooler host.
4. Free projects pause after ~1 week of inactivity; the UptimeRobot pings keep
   both Render and Supabase warm.

Migrations and the cache table are created on every container boot
(idempotent). For a manual run:

```bash
python manage.py migrate
python manage.py createcachetable
```

## 2. API + scheduler (Render)

**Blueprint (recommended)**

1. Render → **New → Blueprint** → select this repo.
2. Render creates `status-monitor-api` (Docker, free plan, health check
   `/api/health`) from `render.yaml`.
3. Fill the `sync: false` values (see the environment reference below):
   `DATABASE_URL`, `ALLOWED_HOSTS`, `FRONTEND_URL`, `SELF_MONITOR_URL`,
   `ADMIN_ALERT_EMAIL`, SMTP values, Polar values.
4. Set `TRUSTED_PROXY_IPS=*` (already in the blueprint).
5. Set `PROXY_HOPS`:
   - `1` while testing the Render URL directly
   - `2` if the SPA calls `/api/*` through Vercel (the default frontend setup)
   - Verify with the diagnostic command after your first browser login:

     ```bash
     python manage.py debug_proxy --latest
     ```

**Manual service** — same settings: runtime Docker, health check
`/api/health`, plan Free, start command from the `Dockerfile`.

> The scheduler lives inside the API container because the free plan has no cron
> add-ons. It sleeps with the service; UptimeRobot's 5-minute `/api/health`
> ping is what keeps it awake. Upgrade to an always-on instance before you rely
> on minute-level checks.

## 3. Frontend (Vercel)

1. Import the repo and set **Root Directory = `frontend`**.
2. Add environment variable `API_ORIGIN` = your Render host, **without scheme**
   (e.g. `status-monitor-api.onrender.com`).
3. `frontend/vercel.json` already provides:
   - `/api/:path*` → `https://$API_ORIGIN/api/:path*` (keeps cookies same-origin)
   - SPA fallback to `/index.html`
   - security headers (CSP, frame-deny, referrer, permissions policy, HSTS)
4. If `$API_ORIGIN` interpolation is unavailable on your plan, replace it with
   the literal host in `vercel.json`.
5. Because the browser sees one origin, the `SameSite=Strict` refresh + CSRF
   cookies work unchanged. Only set `CORS_ALLOWED_ORIGINS` if you call Render
   directly instead of proxying (then cookies need `SameSite=None; Secure`).

## 4. Billing (Polar)

Sandbox first:

```env
POLAR_USE_SANDBOX=True
POLAR_ACCESS_TOKEN=polar_oat_...
POLAR_PRODUCT_PRO=prod_...
POLAR_PRODUCT_BUSINESS=prod_...
POLAR_WEBHOOK_SECRET=whsec_...
FRONTEND_URL=https://your-app.vercel.app
```

- Webhook URL: `https://<render-host>/api/billing/webhook` (Polar sandbox dashboard)
- Sandbox test card: `4242 4242 4242 4242`
- The webhook is HMAC-verified and idempotent (`WebhookEvent` ledger).
- Going live: swap the sandbox token/products/secret, set
  `POLAR_USE_SANDBOX=False`, redeploy, and re-point the production webhook.

## 5. Uptime (UptimeRobot)

| Monitor | URL | Purpose |
|---|---|---|
| API | `https://<render-host>/api/health` | liveness + keeps Render awake |
| Frontend | `https://your-app.vercel.app` | Vercel availability |
| Feed | `https://<render-host>/api/public/monitors` | proves the public feed works |

Use a 5-minute interval. Do not use GitHub Actions as the uptime monitor —
scheduled runs are delayed and consume quota. `cron.yml` is manual-only and
skips everything until `API_BASE_URL` + `SCHEDULER_TOKEN` are set.

## 6. Environment reference

The full copy-paste template lives in [`render.env.example`](../render.env.example).
`★` = secret (set only in Render), `⚙` = generated by the blueprint.

| Variable | Default / example | Notes |
|---|---|---|
| `DEBUG` | `False` | must be False in production |
| `SECRET_KEY` ★ | random 64 chars | Django signing |
| `JWT_SIGNING_KEY` ★ | independent random | JWT HS256 signing |
| `ALLOWED_HOSTS` | `status-monitor-api.onrender.com` | `RENDER_EXTERNAL_HOSTNAME` is auto-added |
| `DATABASE_URL` ★ | Supabase pooler DSN | switches cache to the DB cache |
| `DB_CONN_MAX_AGE` | `60` | seconds |
| `COOKIE_SECURE` | `True` | defaults to `not DEBUG` |
| `SECURE_SSL_REDIRECT` | `True` | enables HSTS + secure cookies |
| `TRUSTED_PROXY_IPS` | `*` | only behind a proxy you control |
| `PROXY_HOPS` | `1` (direct) / `2` (Vercel proxy) | X-Forwarded-For depth |
| `SESSION_COOKIE_AGE` | `1800` | admin/session lifetime |
| `FRONTEND_URL` | Vercel URL | Polar redirects / links |
| `CORS_ALLOWED_ORIGINS` | empty | only for direct API calls |
| `SCHEDULER_TOKEN` ★ ⚙ | random | `X-Scheduler-Token` for `/api/admin/scheduler/*` |
| `ADMIN_ENABLED` | `False` | opt-in Django admin |
| `ADMIN_PATH` | `/ops-<random>/` | secret URL, not security by itself |
| `ADMIN_IP_ALLOWLIST` | empty | CIDR list or `*` |
| `ADMIN_ALERT_EMAIL` | alerts address | block/new-IP alerts |
| `ADMIN_LOGIN_*` | 5 failures / 15 min / 1 h | admin lockout tuning |
| `LOGIN_MAX_FAILURES` | `10` | per-username app login lockout |
| `LOGIN_LOCK_WINDOW` / `LOGIN_LOCK_SECONDS` | `900` / `600` | failure window / lock duration |
| `HEALTH_VERBOSE` | `False` | expose failure details on `/api/health` (debug only) |
| `EMAIL_*` / `DEFAULT_FROM_EMAIL` | SMTP provider | required for real email |
| `POLAR_*` ★ | sandbox first | billing |
| `REGION_NAME` | `render` | stamped on every Check |
| `SELF_MONITOR_URL` | Vercel URL | your own front door |
| `SENTRY_DSN` | empty | optional error reporting |

## 7. Verify after the first deploy

```bash
curl -sS https://<render-host>/api/health           # {"db":"ok","cache":"ok",...}
curl -sS https://your-app.vercel.app/               # SPA
curl -sS https://<render-host>/api/public/monitors   # public feed
```

In Render logs you should see the boot sequence (`migrate`, `createcachetable`,
`scheduler started`, gunicorn) and a `scheduler minute job ...` line every
minute while the service is awake.

Then, from the Vercel SPA: register → verify email → create a monitor → confirm
the dashboard updates, and check `python manage.py debug_proxy --latest` to
confirm the client IP is the browser IP (not the Vercel edge IP). If it shows the
edge IP, set `PROXY_HOPS=2` and redeploy.

## 8. Free-tier behaviour

- **Render free** sleeps after ~15 min without traffic. The scheduler pauses
  with it. UptimeRobot's 5-minute `/api/health` ping keeps it warm; this is
  enough for a hobby deployment but not a 99.9% SLA. Upgrade when you have
  paying users.
- **Supabase free**: ~500 MB storage. `Check` rows grow with every probe — run
  `manage.py prune_history` (also scheduled daily by `run_scheduler`) and watch
  the table size.
- **Vercel Hobby**: static hosting + rewrites are free; the API is served by
  Render, so Vercel function limits are irrelevant.
- **Polar**: sandbox is free; production fees are per-transaction.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/api/health` 503, `db: err` | Supabase paused / wrong DSN / pooler port | restore the project, check `sslmode=require` |
| Everyone gets 429 on login/refresh | shared proxy IP + low per-IP limits | set `PROXY_HOPS` correctly; per-username lockout is separate |
| Login says "too many failed attempts" for a valid user | per-username lockout | wait `LOGIN_LOCK_SECONDS` or clear the cache key; check `AuditLogEntry` |
| Scheduler not running | Render asleep, or process crashed | ping `/api/health`, check boot logs for `scheduler started` |
| Webhook 400 | wrong `POLAR_WEBHOOK_SECRET` / body modified by a proxy | re-copy the secret; verify no body transformation |
| Admin 404 | `ADMIN_ENABLED=False` (correct default) | enable temporarily, then disable |
| Admin login asks for a device | no confirmed TOTP | enrol at `/security` as a superuser first |
| `You are authenticated but not authorized` | `is_staff` without `is_superuser` | grant superuser deliberately |
| Docker build includes local DB/secrets | `.dockerignore` missing/edited | keep it committed |

## 10. Rollback and updates

- Render deploys are git-push based; use **Rollback** in the dashboard for an
  instant previous-image rollback.
- Migrations are forward-only in normal operation — write a reverse migration
  or restore from a Supabase backup if a rollback crosses a schema change.
- Rotating `SECRET_KEY` / `JWT_SIGNING_KEY` invalidates existing sessions and
  JWTs (expected); rotate during low traffic.
- Rotating `SCHEDULER_TOKEN` requires updating the external scheduler/workflow.

## 11. Security checklist before opening signups

- [ ] `DEBUG=False`, `COOKIE_SECURE=True`, `SECURE_SSL_REDIRECT=True`
- [ ] `ADMIN_ENABLED=False`
- [ ] `TRUSTED_PROXY_IPS` matches the proxy topology; `PROXY_HOPS` verified
- [ ] SMTP configured and `ADMIN_ALERT_EMAIL` set
- [ ] Polar webhook secret set and test purchase completed
- [ ] `manage.py prune_history` scheduled (it is, via `run_scheduler`)
- [ ] Policies seeded and `TOS_VERSION` bumped
- [ ] UptimeRobot monitors green


