# ADR 0004 — Supabase pooler + database-backed cache

- **Status:** accepted
- **Date:** 2026-11-23

## Context

Supabase's direct database endpoint is IPv6-only in several regions; Render's
free egress is IPv4. Free projects also pause when idle. Rate limits and
health checks need a shared cache across gunicorn workers.

## Decision

- Use the Supabase **pooler** DSN with `?sslmode=require` in `DATABASE_URL`.
  Transaction mode (6543) is the default; session mode (5432) is the fallback
  for long-lived worker errors.
- When `DATABASE_URL` is present, `CACHES` switches to `DatabaseCache`
  (`django_cache` table), created by `manage.py createcachetable` on boot.
- Keep `CONN_MAX_AGE` modest (60 s) because the pooler multiplexes connections.

## Consequences

- Throttles, locks and scheduler daily slots are shared across workers and
  survive restarts.
- An extra table in Postgres; prune it via Django's culling plus `prune_history`
  housekeeping.
- A paused database takes the whole app down; `/api/health` reports it and
  UptimeRobot alerts.
- Moving to Redis later only changes the `CACHES` block.
