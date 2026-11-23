# ADR 0001 — Run the scheduler inside the web container

- **Status:** accepted (free-tier deployment)
- **Date:** 2026-11-23

## Context

The app needs minute-granular checks and notification delivery. Render's free
plan has no cron jobs/add-ons, GitHub Actions scheduled runs are delayed and
consume the free 2,000-minute quota, and a separate worker service would be a
second always-on cost.

## Decision

Ship `manage.py run_scheduler` in the same Docker image. The start command runs
migrations, starts the scheduler in the background, then execs gunicorn.
Daily jobs use UTC slots with a per-day cache key so a missed slot runs on the
next wake. External HTTP triggers (`/api/admin/scheduler/*` with
`X-Scheduler-Token`) remain available as a backstop.

## Consequences

- One process to deploy, one free instance, no cron configuration.
- The scheduler sleeps when the free instance spins down; UptimeRobot's
  5-minute `/api/health` ping is the wake mechanism.
- No distributed lock: run exactly one scheduler per database. Horizontal
  scaling requires an advisory lock or a dedicated worker (revisit then).
- Jobs must be idempotent and bounded (crawl limits, wall-clock budgets).
