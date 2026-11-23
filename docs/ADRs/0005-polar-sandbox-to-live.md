# ADR 0005 — Polar: sandbox first, webhook-first state

- **Status:** accepted
- **Date:** 2026-11-23

## Context

Billing must be testable without moving money, and must not trust client-side
success redirects. Polar is merchant of record.

## Decision

- `POLAR_USE_SANDBOX` selects the sandbox API; product ids and tokens are
  env-specific.
- Local state is driven by **signed webhooks** (`Webhook-Id` deduplicated in
  `WebhookEvent`), not by the checkout success page.
- Checkout/portal URLs are created server-side for the authenticated user; the
  SPA only redirects.
- Email verification is required before checkout.
- Going live is an env swap plus a webhook re-point, documented in
  `DEPLOYMENT.md`.

## Consequences

- Sandbox purchases exercise the same code path as production.
- Replaying a webhook is safe (idempotency ledger).
- A wrong secret or a proxy that rewrites the raw body produces 400s; the
  runbook covers it.
- Plan limits are enforced from the local `Subscription` row, so webhook delays
  briefly delay upgrades/downgrades.
