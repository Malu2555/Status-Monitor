# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project uses semantic
versioning once tagged.

## [Unreleased]

### Added
- In-container scheduler (`manage.py run_scheduler`) with minute and daily jobs,
  plus `prune_history` retention.
- Machine scheduler endpoint `POST /api/admin/scheduler/{job}` authenticated by
  `X-Scheduler-Token`.
- Hardened admin: superuser + TOTP (`OTPAdminSite`), login lockout, optional IP
  allow-list, environment-gated path, secure short sessions.
- Moderation CLI (`manage.py moderate`) and `debug_proxy` diagnostics.
- Render blueprint, Vercel proxy config, `.dockerignore`, SMTP settings,
  deployment/security/runbook docs and ADRs.
- Pyright is now clean (0 errors) and blocking in CI; the toolchain is pinned
  (`pyright`, `django-stubs`, `ruff`) and the temporary error-budget ratchet was
  removed. A Docker build + `/api/health` smoke test runs in CI.

### Changed
- Admin job triggers now require superuser; staff retains moderation API access.
- Rate-limit identity uses trusted-proxy-aware client IP and hop count.
- Health endpoint no longer exposes failure details in production.

### Fixed
- Notification webhook/Slack/Discord channels validate against SSRF at create
  and dispatch time.
- Unbounded growth of check history, abuse events, audit rows and the outbox.
- Refresh no longer shares the 5/min login bucket behind a shared proxy IP.
- Email notification channels are restricted to the account address.

### Security
- Permissions-Policy and SPA security headers added.
- OpenAPI docs disabled when `DEBUG=False`.
- Per-username login lockout independent of IP.

## [0.1.0] - initial development snapshot
- Uptime, keyword, domain-expiry, TLS and broken-link monitoring; status pages;
  Polar billing; 2FA; audit log; notification outbox; mobile/light-dark landing.
