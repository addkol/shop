import secrets

from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import connection
from django.http import JsonResponse


def health_check(request):
    component_checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        component_checks["database"] = "unavailable"
    else:
        component_checks["database"] = "ok"

    cache_key = f"health:{secrets.token_hex(8)}"
    try:
        cache.set(cache_key, "ok", timeout=10)
        component_checks["cache"] = "ok" if cache.get(cache_key) == "ok" else "unavailable"
        cache.delete(cache_key)
    except Exception:
        component_checks["cache"] = "unavailable"

    if settings.USE_S3:
        try:
            default_storage.exists(".healthcheck")
        except Exception:
            component_checks["storage"] = "unavailable"
        else:
            component_checks["storage"] = "ok"

    status = "ok" if all(value == "ok" for value in component_checks.values()) else "unavailable"
    return JsonResponse(
        {"status": status, "checks": component_checks},
        status=200 if status == "ok" else 503,
    )


def liveness_check(request):
    return JsonResponse({"status": "ok"})
