# Contributing

Thanks for helping improve Status Monitor. Start here, then read
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/SECURITY.md`](docs/SECURITY.md) before touching auth, billing or the
scheduler.

## Setup

```bash
# from the repository root
python -m venv .venv
. .venv/Scripts/Activate.ps1        # Windows PowerShell
pip install -r backend/requirements.txt -r backend/requirements-dev.txt -c backend/constraints.txt

cd backend
python manage.py migrate
python manage.py runserver          # http://127.0.0.1:8000
cd ../frontend
npm install
npm run dev                         # http://localhost:5173 (proxies /api)
```

Copy `backend/.env.example` to `backend/.env` for local overrides. Never commit
it; the repository ignores `*.env` and keeps only `*.env.example` templates.
`DEBUG=False` requires a `SECRET_KEY` of at least 50 characters (the dev fallback
is only used when `DEBUG=True`).

## Dependency pinning

`backend/constraints.txt` is a pinned snapshot of the dependency closure, used by
CI and the Docker image (`pip install ... -c constraints.txt`) so all three
environments install the same versions. Upgrade deliberately:

```bash
cd backend
python -m pip install -U <package>
python scripts/gen_constraints.py
git diff constraints.txt      # review the change, then run the checks below
```

Never hand-edit `constraints.txt`; regenerate it. If a pin is wrong, fix the
package version or the generator.

Useful one-off commands:

```bash
python manage.py run_scheduler --once --all     # run every job once
python manage.py moderate list_recent --days 7
python manage.py debug_proxy --latest
python manage.py export_openapi                 # regenerate the schema
```

## Checks (must pass before a PR)

```bash
cd backend
ruff check .
python manage.py makemigrations --check --dry-run
python manage.py test
pyright                     # must report zero errors (blocking in CI)

cd ../frontend
npm run lint
npm run build
npm run audit:mobile        # optional: needs a local Chrome
```

CI treats ruff, pyright, tests, migration drift, frontend lint/build and gitleaks
as blocking. `pip-audit` is informational. `pyright` must report **zero**
errors; the analysis toolchain (`pyright`, `django-stubs`, `ruff`) is pinned in
`requirements*.txt` so CI matches a local run. A separate CI job builds the
Docker image and smoke-tests `GET /api/health`; Render builds the same image at
deploy time.

## Conventions

- **Python:** ruff formatting, type hints on public functions, services own
  business logic, routers stay thin. New outbound HTTP goes through
  `backend/core/net.py`.
- **Django:** one app per domain; every model change ships with a migration and
  a test; never put secrets in audit payloads.
- **API:** update schemas and run `export_openapi` + `npm run api:gen`; document
  new endpoints in `docs/API.md` if they are user-facing.
- **Frontend:** composition API + `<script setup>`, design tokens only (no raw
  colors), 44px touch targets, keyboard-accessible controls.
- **Security:** never log tokens/passwords; treat notification addresses as
  secrets; add a regression test for every auth/abuse fix.
- **Tests:** a test that intentionally fails auth must clear the cache in
  `tearDown` (abuse counters and login locks live in the shared cache, which is
  not rolled back with the database).
- **Docs:** architecture decisions go in `docs/ADRs/`; runbook changes in
  `docs/RUNBOOK.md`; env changes in `docs/DEPLOYMENT.md` +
  `render.env.example`.

## Pull request checklist

- [ ] Tests cover the change (happy path + failure/abuse path)
- [ ] `ruff`, migrations check, backend tests, frontend lint/build pass
- [ ] `ruff` / `pyright` clean (zero errors), tests and frontend build pass
- [ ] No secrets, `.env` files or generated artifacts committed
- [ ] Docs/ADRs updated when behaviour or environment changes
- [ ] Screenshots or a short clip for UI changes
