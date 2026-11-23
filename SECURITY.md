# Security policy

## Supported versions

Security fixes are applied to the default branch. If you run a fork, rebase on
the latest `main` before reporting an issue.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Email the maintainer at **security@example.com** (replace with a monitored
address before publishing) with:

- a description and impact assessment,
- reproduction steps or a proof of concept,
- affected commit/version and deployment shape (Render/Vercel/Supabase),
- whether the issue is already public.

You can expect an acknowledgement within 72 hours and a remediation plan within
7 days for confirmed issues. Please allow a reasonable disclosure window
(typically 90 days) before publishing details.

## Scope

In scope: this repository's application code, authentication/session handling,
authorization boundaries, SSRF protections, billing webhook verification, admin
surface, CI configuration, and deployment defaults.

Out of scope: findings that require a compromised host/browser, denial of service
by sheer volume beyond the documented free-tier limits, social engineering, and
issues in third-party services (report those to Render/Vercel/Supabase/Polar).

## Safe harbour

Good-faith research that respects user privacy, avoids data destruction, and does
not pivot into other tenants' data is welcome. Do not test against production
accounts you do not own; use a local instance (`DEBUG=True`, SQLite) where
possible.

## Hardening references

- [`docs/SECURITY.md`](docs/SECURITY.md) — threat model and controls
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — production configuration
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — incident response
