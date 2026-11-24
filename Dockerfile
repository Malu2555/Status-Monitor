# Production image: gunicorn serving Django + the in-container scheduler.
# The free Render tier has no cron add-on, so the minute loop lives here.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt backend/constraints.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt -c /app/constraints.txt

COPY backend /app/backend
WORKDIR /app/backend

# Render (and most PaaS) provide PORT; local docker defaults to 8000.
ENV PORT=8000
EXPOSE 8000

# One-off commands (docker compose run --rm web ...):
#   python manage.py migrate && python manage.py createcachetable
# The start command applies migrations + the cache table (idempotent), starts
# the scheduler in the background, then execs gunicorn (PID 1).
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py createcachetable && (python manage.py run_scheduler &) && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 90 --graceful-timeout 30"]
