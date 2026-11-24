# On-call runbook

Operational procedures for the deployed stack. Deployment steps live in
[`DEPLOYMENT.md`](DEPLOYMENT.md); controls in [`SECURITY.md`](SECURITY.md).

## Daily / weekly checks

- `/api/health` green (UptimeRobot).
- Scheduler heartbeat: Render logs should show
  `scheduler minute job run_checks ...` at least once a minute while awake.
- `manage.py moderate list_recent --days 1` — new blocks and abuse spikes.
- Supabase storage growth; run `prune_history` if `Check` rows dominate.
- Failed notification deliveries (`NotificationDelivery.status=dead`).

## Alerts → first response

### API down / health 503

1. `curl -sS https://<host>/api/health` → which component is `err`?
2. DB error → Supabase project paused? connection limit? pooler DSN?
3. Cache error → `django_cache` table missing? run `createcachetable`.
4. If the container is crash-looping, check Render logs for migration errors or
   a bad env var (settings fail fast on purpose).

### Render asleep / checks delayed

Free instances sleep after ~15 min idle. Confirm UptimeRobot is pinging
`/api/health`. A sleeping instance is expected to miss probes; upgrade the plan
if that is unacceptable.

### Scheduler stopped (health green)

1. Render logs: search for `Scheduler started`; if absent, the background
   process died. Restart the service.
2. Run once manually to see the error:

   ```bash
   python manage.py run_scheduler --once --all
   ```

3. Common causes: a provider timeout in `run_checks`, bad cron job allow-list,
   disk/DB full.

### Login-rate-limit complaints

- Check `PROXY_HOPS` and `TRUSTED_PROXY_IPS`; run
  `python manage.py debug_proxy --latest`. A wrong hop count makes every user
  share one throttle bucket.
- Per-username lockout clears after `LOGIN_LOCK_SECONDS` (default 10 min). The
  cache key is `login:fail:user:<username>` / `login:lock:<username>`; delete via
  the cache backend only if the user is verified.
- Never lift an auto IP block without checking `AbuseEvent` for the source.

### Admin access

- 404 → `ADMIN_ENABLED=False` (expected). Enable temporarily, redeploy, use it,
  disable again.
- "Authenticated but not authorized" → account lacks `is_superuser`.
- OTP field missing/refused → enrol TOTP at `/security` first; check the device
  is confirmed.
- Locked out → `BlockedIP` row for your IP; `manage.py moderate unblock_ip`.

### Database growth

```bash
python manage.py prune_history --days 30 --audit-days 180 --abuse-days 90 --dry-run
python manage.py prune_history --days 30 --audit-days 180 --abuse-days 90
```

Scheduled daily at 03:30 UTC by `run_scheduler`. Keep audit rows long enough for
compliance; keep raw `Check` rows short (30–90 days) and rely on 7/30-day
aggregates.

### Polar / billing incidents

- Webhook 400 → secret mismatch or a proxy rewrote the body.
- Duplicate webhook → `WebhookEvent` ledger should suppress it; if not, inspect
  the delivery id header.
- Upgrade not applied → check `Subscription` row and Polar customer id; replay
  the webhook from Polar after verifying the signature.
- Sandbox vs live mix-up → `POLAR_USE_SANDBOX` and product ids must match the
  environment.

### Supabase paused / unreachable

1. Restore the project in the Supabase dashboard.
2. Verify `DATABASE_URL` uses the pooler host and `?sslmode=require`.
3. Re-run `/api/health`; if 503 persists, check connection limits and
   `DB_CONN_MAX_AGE` (lower it if the pooler is saturated).

## Secret rotation

| Secret | Effect | Procedure |
|---|---|---|
| `JWT_SIGNING_KEY` | all sessions/JWTs invalid | rotate, redeploy, users log in again |
| `SECRET_KEY` | sessions + password-reset links invalid | rotate during low traffic |
| `SCHEDULER_TOKEN` | external scheduler stops | update scheduler/workflow in the same window |
| Polar webhook secret | webhooks rejected | update Polar + Render together |
| SMTP password | email delivery fails | rotate at provider, update Render |

Never rotate `SECRET_KEY` casually: Django sessions and signed tokens use it.
Database encryption/rotation is not implemented yet (see `SECURITY.md`).

## Restore drill (quarterly)

1. Create a scratch Supabase project.
2. Restore the latest backup/PITR snapshot.
3. Point a local API at it (`DEBUG=False`, `DATABASE_URL=...`).
4. `manage.py check`, `/api/health`, log in, open a dashboard.
5. Record RTO/RPO and any missing migration.

## Deploy checklist

- [ ] CI green (ruff, pyright, tests, frontend build, gitleaks)
- [ ] `makemigrations --check` clean
- [ ] New env vars documented in `DEPLOYMENT.md` + `render.env.example`
- [ ] Rollback image/commit noted
- [ ] Smoke: health, register/login, create monitor, public feed, checkout (sandbox)
