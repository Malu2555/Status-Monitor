# Production image: gunicorn serving the Django app (PostgreSQL via DATABASE_URL).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend /app/backend
WORKDIR /app/backend

EXPOSE 8000

# First deploy one-offs (run after `docker compose run`):
#   python manage.py migrate && python manage.py createcachetable
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
