from urllib.parse import urlparse
import re

from django.conf import settings
from django.core import checks


def _error(message, error_id):
    return checks.Error(message, id=error_id)


def _configured(value):
    normalized = str(value or "").strip().lower()
    return bool(normalized) and not any(marker in normalized for marker in ("replace-me", "replace-with", "change-me"))


@checks.register(checks.Tags.security, deploy=True)
def production_configuration_check(app_configs, **kwargs):
    if settings.ENVIRONMENT != "production":
        return []

    errors = []
    if settings.DEBUG:
        errors.append(_error("DEBUG должен быть отключён в production.", "project.E001"))
    if len(settings.SECRET_KEY) < 50 or "change-me" in settings.SECRET_KEY:
        errors.append(_error("SECRET_KEY недостаточно надёжен.", "project.E002"))
    if not settings.DATABASES["default"]["ENGINE"].endswith("postgresql"):
        errors.append(_error("Production должен использовать PostgreSQL.", "project.E003"))

    site_url = urlparse(settings.SITE_URL)
    if site_url.scheme != "https" or not site_url.hostname:
        errors.append(_error("SITE_URL должен быть точным HTTPS-адресом магазина.", "project.E004"))
    if not settings.ALLOWED_HOSTS or any(host == "*" or host.startswith(".") for host in settings.ALLOWED_HOSTS):
        errors.append(_error("ALLOWED_HOSTS должен содержать только точные домены.", "project.E005"))
    if not settings.CSRF_TRUSTED_ORIGINS or any("*" in origin for origin in settings.CSRF_TRUSTED_ORIGINS):
        errors.append(_error("CSRF_TRUSTED_ORIGINS должен содержать точные HTTPS origins.", "project.E006"))
    if site_url.hostname and site_url.hostname not in settings.ALLOWED_HOSTS:
        errors.append(_error("Домен SITE_URL должен присутствовать в ALLOWED_HOSTS.", "project.E024"))
    site_origin = f"{site_url.scheme}://{site_url.netloc}" if site_url.scheme and site_url.netloc else ""
    if site_origin and site_origin not in settings.CSRF_TRUSTED_ORIGINS:
        errors.append(_error("Origin SITE_URL должен присутствовать в CSRF_TRUSTED_ORIGINS.", "project.E025"))

    required_security = (
        (settings.SECURE_SSL_REDIRECT, "SECURE_SSL_REDIRECT", "project.E007"),
        (settings.SESSION_COOKIE_SECURE, "SESSION_COOKIE_SECURE", "project.E008"),
        (settings.CSRF_COOKIE_SECURE, "CSRF_COOKIE_SECURE", "project.E009"),
        (settings.USE_X_FORWARDED_PROTO, "USE_X_FORWARDED_PROTO", "project.E010"),
    )
    for enabled, setting_name, error_id in required_security:
        if not enabled:
            errors.append(_error(f"{setting_name} должен быть включён.", error_id))
    if settings.SECURE_HSTS_SECONDS < 31536000:
        errors.append(_error("SECURE_HSTS_SECONDS должен быть не меньше 31536000.", "project.E011"))

    if "locmem" in settings.CACHES["default"]["BACKEND"].lower():
        errors.append(_error("Production rate limiting требует общего Redis cache.", "project.E012"))
    if not settings.CLIENT_IP_HEADER:
        errors.append(_error("Укажите доверенный CLIENT_IP_HEADER reverse proxy.", "project.E023"))
    elif settings.CLIENT_IP_HEADER not in {"HTTP_X_REAL_IP", "HTTP_X_FORWARDED_FOR"}:
        errors.append(_error("CLIENT_IP_HEADER должен быть X-Real-IP или X-Forwarded-For.", "project.E026"))
    if settings.CLIENT_IP_TRUSTED_HOPS < 1:
        errors.append(_error("CLIENT_IP_TRUSTED_HOPS должен быть не меньше 1.", "project.E027"))
    if settings.CELERY_TASK_ALWAYS_EAGER:
        errors.append(_error("CELERY_TASK_ALWAYS_EAGER должен быть отключён.", "project.E013"))
    if "127.0.0.1" in settings.CELERY_BROKER_URL or "localhost" in settings.CELERY_BROKER_URL:
        errors.append(_error("Укажите внешний CELERY_BROKER_URL.", "project.E014"))

    if settings.FIXED_OTP_CODE:
        pass
    elif settings.SMS_PROVIDER != "twilio":
        errors.append(_error("Production поддерживает только настроенный SMS_PROVIDER=twilio.", "project.E015"))
    elif not all(
        _configured(value)
        for value in [settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_FROM_NUMBER]
    ):
        errors.append(_error("Не заполнены настройки Twilio.", "project.E016"))
    if "console" in settings.EMAIL_BACKEND:
        errors.append(_error("Console email backend запрещён в production.", "project.E017"))
    elif "smtp" in settings.EMAIL_BACKEND and not all(
        _configured(value)
        for value in [settings.EMAIL_HOST, settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD]
    ):
        errors.append(_error("Не заполнены обязательные SMTP-настройки.", "project.E028"))

    if settings.FINIK_USE_STUB:
        errors.append(_error("FINIK_USE_STUB должен быть отключён.", "project.E018"))
    if not all(
        _configured(value)
        for value in [
            settings.FINIK_API_KEY,
            settings.FINIK_ACCOUNT_ID,
            settings.FINIK_PRIVATE_KEY,
            settings.FINIK_WEBHOOK_PUBLIC_KEY,
        ]
    ):
        errors.append(_error("Не заполнены production-ключи Finik.", "project.E019"))
    if urlparse(settings.FINIK_API_URL).hostname != "api.acquiring.averspay.kg":
        errors.append(_error("Production должен использовать production endpoint Finik.", "project.E020"))
    status_url = urlparse(settings.FINIK_STATUS_API_URL.replace("{payment_id}", "test-payment"))
    if status_url.scheme != "https" or status_url.hostname != "api.acquiring.averspay.kg":
        errors.append(
            _error(
                "FINIK_STATUS_API_URL должен быть production HTTPS endpoint Finik.",
                "project.E029",
            )
        )

    if settings.SERVE_MEDIA_FILES:
        errors.append(_error("Django не должен обслуживать media в production.", "project.E021"))
    if settings.USE_S3:
        required_s3 = [
            settings.STORAGES["default"]["OPTIONS"].get("access_key"),
            settings.STORAGES["default"]["OPTIONS"].get("secret_key"),
            settings.STORAGES["default"]["OPTIONS"].get("bucket_name"),
        ]
        if not all(_configured(value) for value in required_s3):
            errors.append(_error("Не заполнены обязательные параметры S3.", "project.E022"))

    if not settings.SENTRY_DSN:
        errors.append(
            checks.Warning(
                "SENTRY_DSN не настроен: ошибки production не будут централизованно собираться.",
                id="project.W001",
            )
        )
    return errors


@checks.register(checks.Tags.security)
def fixed_otp_check(app_configs, **kwargs):
    if not settings.FIXED_OTP_CODE:
        return []
    if not re.fullmatch(r"[0-9]{4}", settings.FIXED_OTP_CODE):
        return [checks.Error("FIXED_OTP_CODE должен содержать ровно четыре ASCII-цифры.", id="project.E030")]
    return [checks.Warning(
        "FIXED_OTP_CODE активирован: SMS отключены, любой знающий общий код может войти под чужим номером. Не используйте реальные клиентские данные и отключите настройку перед продажами.",
        id="project.W002",
    )]
