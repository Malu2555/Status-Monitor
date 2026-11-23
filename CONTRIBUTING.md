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
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

cd backend
python manage.py migrate
python manage.py runserver          # http://127.0.0.1:8000

cd ../frontend
npm install
npm run dev                         # http://localhost:5173 (proxies /api)
```

Copy `backend/.env.example` to `backend/.env` for local overrides. Never commit
it; the repository ignores `*.env` and keeps only `*.env.example` templates.

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
pyright                     # informational; CI enforces the error budget
python scripts/check_pyright_budget.py <current.json> pyright-baseline.json

cd ../frontend
npm run lint
npm run build
npm run audit:mobile        # optional: needs a local Chrome
```

CI treats ruff, tests, migration drift, frontend lint/build and gitleaks as
blocking. `pip-audit` is informational; pyright fails only if the error count
rises above `backend/pyright-baseline.json` (update it deliberately, never to
hide a regression you introduced). A separate CI job builds the Docker image
and smoke-tests `GET /api/health`; Render builds the same image at deploy time.

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
- **Docs:** architecture decisions go in `docs/ADRs/`; runbook changes in
  `docs/RUNBOOK.md`; env changes in `docs/DEPLOYMENT.md` +
  `render.env.example`.

## Pull request checklist

- [ ] Tests cover the change (happy path + failure/abuse path)
- [ ] `ruff`, migrations check, backend tests, frontend lint/build pass
- [ ] No new pyright errors (or baseline updated intentionally)
- [ ] No secrets, `.env` files or generated artifacts committed
- [ ] Docs/ADRs updated when behaviour or environment changes
- [ ] Screenshots or a short clip for UI changes
