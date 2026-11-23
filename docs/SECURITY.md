# Security model

This document describes what is protected, against whom, and where the known
gaps are. Report vulnerabilities per [`/SECURITY.md`](../SECURITY.md); deployment
hardening lives in [`DEPLOYMENT.md`](DEPLOYMENT.md).

## 1. Assets

| Asset | Impact if lost |
|---|---|
| User accounts + password hashes | account takeover, privacy breach |
| Access/refresh tokens | impersonation until expiry/rotation |
| API tokens (`X-API-Key`) | scoped programmatic access |
| Monitor configuration | SSRF pivot, brand/status manipulation |
| Notification secrets (Telegram bot tokens, webhook URLs) | spam, data exfiltration to third parties |
| Audit log | loss of compliance evidence / non-repudiation |
| Billing state + Polar customer ids | fraudulent upgrades, support burden |
| `SECRET_KEY` / `JWT_SIGNING_KEY` / `SCHEDULER_TOKEN` | full auth bypass if leaked |

## 2. Adversaries and trust boundaries

| Adversary | Capability | Primary controls |
|---|---|---|
| Anonymous internet | scan, brute force, spam registration | throttles, honeypot, IP auto-block, email verification |
| Authenticated user | abuse own account, SSRF via monitor/channel URLs, spam email | ownership checks, SSRF guard, plan limits, email-channel restriction |
| Stolen token holder | replay access/refresh/API keys | short access TTL, rotation + reuse detection, token revocation, `is_active` checks |
| Malicious proxy / spoofed headers | fake client IP to evade limits | `TRUSTED_PROXY_IPS` allow-list, `PROXY_HOPS`, rightmost-hop resolution |
| Insider / DB reader | read secrets at rest | least-privilege DB, encryption backlog, audit trail |
| Vendor compromise (Polar/Supabase/Render) | forged webhooks, data access | HMAC webhook verification, delivery idempotency, TLS, scoped keys |

Trust boundaries: browser ↔ Vercel (TLS), Vercel ↔ Render (proxy headers), app ↔
Supabase (TLS, pooler), app ↔ Polar (HMAC), app ↔ notification providers
(user-controlled egress).

## 3. Controls

### Authentication and sessions
- Password hashing via Django defaults (PBKDF2) with Django's four validators.
- Access JWT (HS256, 15 min) held **in memory**; refresh token in an
  `HttpOnly`, `SameSite=Strict`, `path=/api/auth` cookie; CSRF cookie is
  readable and checked with constant-time compare on refresh.
- Refresh rotation: every refresh burns the presented token; reuse is rejected
  via the `RevokedRefreshToken` blacklist.
- `is_active` and `tokens_invalid_before` are checked on every request, so
  disabling an account or changing a password invalidates outstanding tokens.
- Optional TOTP with hashed single-use recovery codes; login demands a code
  when enabled.
- Admin (`/admin`) requires `is_superuser` **and** a verified TOTP device, with
  lockout and optional IP allow-list; disabled by default.

### Authorization
- Every monitor/status-page/channel query is owner-scoped.
- API tokens carry `read`/`write` scope; write endpoints reject read-only keys.
- Moderation endpoints require `is_staff`; scheduler endpoints require a shared
  secret and only allow-listed jobs.
- Admin actions and moderation commands write audit rows.

### Network safety
- All monitor URLs, crawl hops and (now) notification webhooks pass the SSRF
  guard in `core.net`: http/https only, DNS resolution, every resolved address
  must be globally routable, redirects are not followed automatically.
- Outbound requests have explicit timeouts and bounded response sizes.

### Abuse resistance
- Per-IP throttles: auth 5/min (login 10/min), public feed 60/min, envelope
  1500/h, global 2000/h; per-user scopes for writes.
- Per-username login lockout (10 failures/15 min → 10 min) independent of IP.
- Auto IP block after 50 auth failures/hour; honeypot on registration; 256 KB
  body cap.
- Admin login lockout (5 failures/15 min → 1 h) and new-IP email alerts.

### Secrets and transport
- Secrets only in environment variables; no `.env` in git; `.dockerignore`
  keeps them out of images; gitleaks runs in CI.
- Optional field encryption is **not yet implemented** (see gaps).
- TLS terminated by Render/Vercel; secure cookies + HSTS when
  `SECURE_SSL_REDIRECT=True`; `SameSite` cookies scoped to the API path.

### Headers and browser isolation
- API: CSP, `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, `Permissions-Policy`.
- SPA: CSP, frame-deny, referrer, permissions policy and HSTS via
  `frontend/vercel.json`.
- API docs and the OpenAPI schema are disabled when `DEBUG=False`.

### Audit and privacy
- `AuditLogEntry` is append-only from the application's perspective and records
  actor, action, IP and non-secret payload.
- Audit payloads must never contain passwords/tokens; review new events.
- Health endpoint reports component status publicly, details only in logs.

## 4. Known gaps and backlog

| Gap | Risk | Mitigation today | Planned |
|---|---|---|---|
| Notification channel addresses stored plaintext (Telegram bot tokens, secret webhook URLs) | DB/backup reader can impersonate bots | least-privilege DB access, secrets rotation | deterministic encryption **plus** a separate address hash for the uniqueness constraint |
| Client IP behind chained proxies is configuration-driven | wrong hop count → shared buckets / weak blocking | `TRUSTED_PROXY_IPS` + `PROXY_HOPS` + `debug_proxy` | auto-detect trusted Vercel ranges |
| Email notification channel can target any address | spam/phishing relay | account-only restriction (now enforced) + throttle | per-user email quota |
| Per-username login lockout can be triggered deliberately | targeted 10-minute denial of service for a known account | short lock, audit event, IP auto-block still applies | email-based unlock / adaptive delay |
| Admin pages are unstyled without static hosting | usability, not security | break-glass use only | WhiteNoise or CDN |
| Access JWT cannot be revoked before 15 min | short-lived impersonation after logout | `tokens_invalid_before` on password change/disable | per-jti denylist |
| No field-level encryption for PII | DB dump exposes emails | DB access control | app-level encryption |
| No automated dependency upgrade PRs | stale CVEs | pip-audit in CI | Dependabot |
| Frontend has no unit/e2e security tests | regressions in auth UI | mobile audit + manual QA | Vitest + Playwright |

## 5. Production hardening checklist

- [ ] `DEBUG=False`, random `SECRET_KEY`/`JWT_SIGNING_KEY`, `COOKIE_SECURE=True`,
      `SECURE_SSL_REDIRECT=True`
- [ ] `ADMIN_ENABLED=False`; `ADMIN_PATH` random; `ADMIN_IP_ALLOWLIST` set when
      the admin is temporarily enabled
- [ ] `TRUSTED_PROXY_IPS=*` only behind a managed proxy; `PROXY_HOPS` verified
      with `manage.py debug_proxy --latest`
- [ ] SMTP configured; `ADMIN_ALERT_EMAIL` monitored
- [ ] Polar webhook secret set; test purchase verified
- [ ] Supabase DB password rotated from any screenshot/chat; direct DB access
      restricted
- [ ] `prune_history` running daily; `Check` growth watched
- [ ] UptimeRobot monitors for API, SPA and public feed
- [ ] gitleaks + pip-audit + pyright budget green in CI
- [ ] Backups/PITR enabled and a restore has been rehearsed

## 6. Incident response (first 30 minutes)

1. **Contain:** set `ADMIN_ENABLED=False`; rotate `SCHEDULER_TOKEN`; block the
   offending IP (`manage.py moderate block_ip`) or disable the account.
2. **Assess:** `AuditLogEntry` for `auth.login*`, `admin.*`, `moderation.*`,
   `billing.*`; `AbuseEvent` and `BlockedIP`; Render/Vercel logs; Polar dashboard.
3. **Rotate:** `JWT_SIGNING_KEY` (invalidates all sessions), `SECRET_KEY` (also
   invalidates password-reset links), Polar webhook secret, SMTP credentials.
   Rotating `JWT_SIGNING_KEY` is the fastest global logout.
4. **Eradicate:** patch, deploy, verify `/api/health` and a login.
5. **Notify:** affected users and, for billing/PII events, follow your legal
   obligations; Polar can help identify affected customers.
6. **Postmortem:** timeline, root cause, detection gap, action items, add a
   regression test.

## 7. Verification commands

```bash
# Security posture of a deployed instance
curl -sSI https://<host>/api/health | grep -iE 'permissions-policy|content-security|x-frame'
curl -sS https://<host>/api/openapi.json -o /dev/null -w '%{http_code}\n'   # expect 404 in prod

# Proxy attribution (run where the Django app + DB are reachable)
python manage.py debug_proxy --latest
python manage.py debug_proxy --remote 10.0.0.1 --xff "6.6.6.6, 1.2.3.4"

# Locked accounts / blocks
python manage.py moderate list_recent --days 7
```

## 8. Security-relevant tests

- `accounts/tests_admin_security.py` — superuser-only admin, TOTP login, lockout,
  allow-list, Permissions-Policy.
- `accounts/tests_abuse.py` — honeypot, auto-block, client IP / hop resolution,
  throttle identity.
- `accounts/tests_otp.py`, `tests_recovery.py` — 2FA and recovery codes.
- `accounts/tests_auth.py` (login/refresh/rotation/CSRF) and `tests_policy.py`
  (moderation).
- `notifications/tests.py` — channel validation, SSRF rejection, outbox.
- `billing/tests.py` — signature verification and replay idempotency.
- `monitors/tests.py` — SSRF rejection on monitor creation.

