# ADR 0003 — Trust proxy headers explicitly; count hops

- **Status:** accepted
- **Date:** 2026-11-23

## Context

Behind Render (and optionally Vercel), the socket peer is a proxy. Rate
limiting, auto-blocking, audit and JWT throttles need the real client IP, but
naively trusting `X-Forwarded-For` lets clients spoof it. With a chained
Vercel→Render setup the chain length changes, which can collapse every user into
one bucket and turn a 5/min login limit into a global denial of service.

## Decision

- `TRUSTED_PROXY_IPS` lists peers allowed to supply `X-Forwarded-For` (`*` for
  a managed edge that always overwrites/appends).
- `PROXY_HOPS` states how many trailing entries were appended by trusted
  proxies; the resolver picks the entry at `-PROXY_HOPS` (default 1 = rightmost).
- All IP consumers (abuse, audit, ninja throttles) use
  `accounts.abuse.client_ip`.
- `manage.py debug_proxy --latest` prints the raw chain and the resolved IP so
  the hop count can be verified after deployment.
- Per-username login lockout and a per-token refresh throttle reduce reliance on
  IP identity.

## Consequences

- Correct configuration is required after a topology change; docs and a
  diagnostic command make this testable.
- A direct attacker can still forge headers if they can reach the origin
  directly; the Render service should remain proxy-only.
