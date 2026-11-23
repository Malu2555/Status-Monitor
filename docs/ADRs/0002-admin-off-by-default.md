# ADR 0002 — Django admin is off by default and superuser + TOTP only

- **Status:** accepted
- **Date:** 2026-11-23

## Context

`is_staff` previously unlocked the Django admin, the moderation API and the
scheduler job triggers. The admin is a large, attractive attack surface
(session cookie, password reset, model mutations) and routine moderation does
not need it.

## Decision

- `ADMIN_ENABLED` defaults to `False` when `DEBUG=False`; the URL is not
  registered at all when disabled.
- Admin access requires `is_superuser` **and** a verified TOTP device
  (`OTPAdminSite`), with a short session, login lockout, optional IP allow-list
  and a configurable path.
- Scheduler jobs require `is_superuser` for humans, or `X-Scheduler-Token` for
  machines.
- Routine moderation moves to `manage.py moderate ...`.

## Consequences

- Staff accounts alone can no longer reach the admin.
- Operators must enrol TOTP at `/security` before their first admin login.
- Admin pages are unstyled without static hosting; acceptable for break-glass
  use.
- The admin remains available for incident response by flipping one env var.
