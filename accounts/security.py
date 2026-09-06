import hashlib
import ipaddress
import logging

from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger("accounts.auth")


def get_client_ip(request):
    header_name = settings.CLIENT_IP_HEADER
    if header_name:
        forwarded_value = request.META.get(header_name, "")
        addresses = [value.strip() for value in forwarded_value.split(",") if value.strip()]
        trusted_hops = max(1, settings.CLIENT_IP_TRUSTED_HOPS)
        if len(addresses) >= trusted_hops:
            candidate = addresses[-trusted_hops]
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                logger.warning("Получен некорректный IP в доверенном proxy-заголовке.")

    remote_address = request.META.get("REMOTE_ADDR", "")
    try:
        return str(ipaddress.ip_address(remote_address))
    except ValueError:
        return "unknown"


def _rate_key(namespace, identifier):
    digest = hashlib.sha256(str(identifier).encode("utf-8")).hexdigest()
    return f"rate:{namespace}:{digest}"


def consume_rate_limit(namespace, identifier, limit, window_seconds):
    key = _rate_key(namespace, identifier)
    try:
        if cache.add(key, 1, timeout=window_seconds):
            return True
        return cache.incr(key) <= limit
    except Exception:
        logger.exception("Rate limit cache недоступен для %s.", namespace)
        return settings.DEBUG


def reset_rate_limit(namespace, identifier):
    try:
        cache.delete(_rate_key(namespace, identifier))
    except Exception:
        logger.exception("Не удалось сбросить rate limit для %s.", namespace)
