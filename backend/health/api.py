"""GET /api/health — unauthenticated liveness probe for orchestrators.

Runs a DB query (SELECT 1) and a cache set/get round-trip, returning 200 with
a JSON body when everything is fine or 503 naming the failing component.
Auth and throttling are bypassed so load balancers and k8s probes can hit it
freely — this is intentionally separate from the public status feed.
"""
import json
import logging
from datetime import UTC, datetime

from django.core.cache import caches
from django.db import connection
from django.http import HttpResponse
from ninja import Router

logger = logging.getLogger("health")

router = Router(auth=None)


def _first_error_line(exc: Exception) -> str:
    lines = str(exc).splitlines() or [""]
    return lines[0][:120]


def _database_ok() -> tuple[bool, str]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, "ok"
    except Exception as exc:  # DatabaseError / OperationalError / InterfaceError …
        return False, f"{type(exc).__name__}: {_first_error_line(exc)}"


def _cache_ok() -> tuple[bool, str]:
    try:
        cache = caches["default"]
        cache.set("__health__", "ok", timeout=10)
        if cache.get("__health__") != "ok":
            return False, "round-trip mismatch"
        return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {_first_error_line(exc)}"


@router.get("/health", auth=None, throttle=[], url_name="health")
def health(request):
    db_ok, db_detail = _database_ok()
    cache_ok, cache_detail = _cache_ok()
    healthy = db_ok and cache_ok
    body: dict = {
        "db": "ok" if db_ok else "err",
        "cache": "ok" if cache_ok else "err",
        "status": "ok" if healthy else "degraded",
        "ts": datetime.now(UTC).isoformat(),
    }
    if not healthy:
        body["details"] = {
            "db": "ok" if db_ok else db_detail,
            "cache": "ok" if cache_ok else cache_detail,
        }
        logger.error(
            "health probe degraded: db=%s cache=%s db-detail=%s cache-detail=%s",
            db_ok,
            cache_ok,
            db_detail,
            cache_detail,
        )
        return HttpResponse(json.dumps(body), status=503, content_type="application/json")
    logger.info("health probe ok")
    return HttpResponse(json.dumps(body), status=200, content_type="application/json")
