from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from django.contrib.messages import constants as message_constants
from django.core.exceptions import ImproperlyConfigured
from decouple import Csv, config


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="change-me-in-production")
DEBUG = config("DEBUG", default=True, cast=bool)
ENVIRONMENT = config("ENVIRONMENT", default="development" if DEBUG else "production").lower()
if not DEBUG and SECRET_KEY == "change-me-in-production":
    raise ImproperlyConfigured("Для production необходимо задать безопасный SECRET_KEY.")
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="127.0.0.1,localhost", cast=Csv())
DEFAULT_CSRF_TRUSTED_ORIGINS = "https://*.trycloudflare.com" if DEBUG else ""
CSRF_TRUSTED_ORIGINS = [
    origin
    for origin in config(
        "CSRF_TRUSTED_ORIGINS",
        default=DEFAULT_CSRF_TRUSTED_ORIGINS,
        cast=Csv(),
    )
    if origin
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "project.apps.ProjectConfig",
    "accounts",
    "shop",
    "payment",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "project.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shop.context_processors.cart_summary",
                "accounts.context_processors.otp_mode",
            ],
        },
    },
]

WSGI_APPLICATION = "project.wsgi.application"
ASGI_APPLICATION = "project.asgi.application"

def database_from_url(database_url):
    parsed = urlparse(database_url)
    engine_by_scheme = {
        "postgres": "django.db.backends.postgresql",
        "postgresql": "django.db.backends.postgresql",
        "sqlite": "django.db.backends.sqlite3",
    }
    engine = engine_by_scheme.get(parsed.scheme)
    if not engine:
        raise ValueError(f"Unsupported database scheme: {parsed.scheme}")
    if engine == "django.db.backends.sqlite3":
        return {
            "ENGINE": engine,
            "NAME": unquote(parsed.path.lstrip("/")) or BASE_DIR / "db.sqlite3",
        }
    database_config = {
        "ENGINE": engine,
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
    }
    query_options = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
    if query_options:
        database_config["OPTIONS"] = query_options
    return database_config


DATABASE_URL = config("DATABASE_URL", default="")
DB_ENGINE = config("DB_ENGINE", default="django.db.backends.sqlite3")
DB_CONN_MAX_AGE = config("DB_CONN_MAX_AGE", default=0 if DEBUG else 60, cast=int)
if DATABASE_URL:
    DATABASES = {"default": database_from_url(DATABASE_URL)}
elif DB_ENGINE == "django.db.backends.sqlite3":
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": Path(config("SQLITE_NAME", default=str(BASE_DIR / "db.sqlite3"))),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": config("DB_NAME", default="online_shop"),
            "USER": config("DB_USER", default="postgres"),
            "PASSWORD": config("DB_PASSWORD", default="postgres"),
            "HOST": config("DB_HOST", default="127.0.0.1"),
            "PORT": config("DB_PORT", default="5432"),
        }
    }

if not DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    DATABASES["default"]["CONN_MAX_AGE"] = DB_CONN_MAX_AGE
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "accounts.auth_backends.PhoneOrEmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru"
TIME_ZONE = config("TIME_ZONE", default="Asia/Bishkek")
USE_I18N = True
USE_TZ = True

STATIC_URL = config("STATIC_URL", default="static/")
STATIC_ROOT = Path(config("STATIC_ROOT", default=str(BASE_DIR / "staticfiles")))
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = config("MEDIA_URL", default="/media/")
MEDIA_ROOT = Path(config("MEDIA_ROOT", default=str(BASE_DIR / "media")))
SERVE_MEDIA_FILES = config("SERVE_MEDIA_FILES", default=DEBUG, cast=bool)
USE_S3 = config("USE_S3", default=False, cast=bool)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
if USE_S3:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": config("S3_ACCESS_KEY_ID"),
            "secret_key": config("S3_SECRET_ACCESS_KEY"),
            "bucket_name": config("S3_BUCKET_NAME"),
            "endpoint_url": config("S3_ENDPOINT_URL", default="") or None,
            "region_name": config("S3_REGION_NAME", default="") or None,
            "custom_domain": config("S3_CUSTOM_DOMAIN", default="") or None,
            "querystring_auth": config("S3_QUERYSTRING_AUTH", default=False, cast=bool),
            "file_overwrite": False,
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o2750

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "shop:index"
LOGOUT_REDIRECT_URL = "shop:index"
MESSAGE_TAGS = {
    message_constants.ERROR: "danger",
}

EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Online Shop <noreply@example.com>")
EMAIL_HOST = config("EMAIL_HOST", default="smtp.example.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=True, cast=bool)
CELERY_BEAT_SCHEDULE = {
    "reconcile-pending-payments": {
        "task": "payment.tasks.reconcile_pending_payments_task",
        "schedule": config("FINIK_RECONCILIATION_INTERVAL_SECONDS", default=60, cast=int),
    },
    "cancel-expired-orders": {
        "task": "shop.tasks.cancel_expired_orders_task",
        "schedule": config("ORDER_EXPIRY_CHECK_SECONDS", default=60, cast=int),
    },
    "purge-old-payment-payloads": {
        "task": "payment.tasks.purge_old_payment_payloads_task",
        "schedule": 86400,
    },
}

CACHE_URL = config("CACHE_URL", default="")
CACHES = {
    "default": {
        "BACKEND": (
            "django.core.cache.backends.redis.RedisCache"
            if CACHE_URL
            else "django.core.cache.backends.locmem.LocMemCache"
        ),
        **({"LOCATION": CACHE_URL} if CACHE_URL else {"LOCATION": "online-shop"}),
    }
}

TWILIO_ACCOUNT_SID = config("TWILIO_ACCOUNT_SID", default="")
TWILIO_AUTH_TOKEN = config("TWILIO_AUTH_TOKEN", default="")
TWILIO_FROM_NUMBER = config("TWILIO_FROM_NUMBER", default="")
SMS_PROVIDER = config("SMS_PROVIDER", default="console")
FIXED_OTP_CODE = config("FIXED_OTP_CODE", default="").strip()
SMS_CODE_TTL_SECONDS = config("SMS_CODE_TTL_SECONDS", default=300, cast=int)
SMS_MAX_ATTEMPTS = config("SMS_MAX_ATTEMPTS", default=5, cast=int)
SMS_RESEND_COOLDOWN_SECONDS = config("SMS_RESEND_COOLDOWN_SECONDS", default=60, cast=int)
SMS_REQUEST_WINDOW_SECONDS = config("SMS_REQUEST_WINDOW_SECONDS", default=3600, cast=int)
SMS_MAX_REQUESTS_PER_WINDOW = config("SMS_MAX_REQUESTS_PER_WINDOW", default=5, cast=int)
SMS_IP_MAX_REQUESTS_PER_WINDOW = config("SMS_IP_MAX_REQUESTS_PER_WINDOW", default=20, cast=int)
ADMIN_LOGIN_MAX_ATTEMPTS = config("ADMIN_LOGIN_MAX_ATTEMPTS", default=5, cast=int)
ADMIN_LOGIN_WINDOW_SECONDS = config("ADMIN_LOGIN_WINDOW_SECONDS", default=900, cast=int)
ADMIN_EMAIL_VERIFICATION_TTL_SECONDS = config(
    "ADMIN_EMAIL_VERIFICATION_TTL_SECONDS",
    default=86400,
    cast=int,
)
ORDER_PAYMENT_TTL_MINUTES = config("ORDER_PAYMENT_TTL_MINUTES", default=30, cast=int)

SITE_URL = config("SITE_URL", default="http://127.0.0.1:8000")
FINIK_API_URL = config("FINIK_API_URL", default="https://beta.api.acquiring.averspay.kg/v1/payment")
FINIK_STATUS_API_URL = config(
    "FINIK_STATUS_API_URL",
    default="" if ENVIRONMENT == "production" else f"{FINIK_API_URL.rstrip('/')}/{{payment_id}}",
)
FINIK_API_KEY = config("FINIK_API_KEY", default="")
FINIK_ACCOUNT_ID = config("FINIK_ACCOUNT_ID", default="")
FINIK_DISPLAY_NAME = config("FINIK_DISPLAY_NAME", default="Elit Market")
FINIK_PRIVATE_KEY = config("FINIK_PRIVATE_KEY", default="")
FINIK_WEBHOOK_PUBLIC_KEY = config("FINIK_WEBHOOK_PUBLIC_KEY", default="")
FINIK_WEBHOOK_TOLERANCE_SECONDS = config("FINIK_WEBHOOK_TOLERANCE_SECONDS", default=300, cast=int)
FINIK_USE_STUB = config("FINIK_USE_STUB", default=True, cast=bool)
PAYMENT_ENABLED = config("PAYMENT_ENABLED", default=True, cast=bool)
ADMIN_EMAIL_VERIFICATION_ENABLED = config("ADMIN_EMAIL_VERIFICATION_ENABLED", default=True, cast=bool)
FINIK_TIMEOUT = config("FINIK_TIMEOUT", default=15, cast=int)
FINIK_STATUS_MAX_BODY_BYTES = config("FINIK_STATUS_MAX_BODY_BYTES", default=65536, cast=int)
FINIK_RECONCILIATION_INTERVAL_SECONDS = config(
    "FINIK_RECONCILIATION_INTERVAL_SECONDS",
    default=60,
    cast=int,
)
FINIK_RECONCILIATION_BATCH_SIZE = config("FINIK_RECONCILIATION_BATCH_SIZE", default=100, cast=int)
FINIK_RECONCILIATION_MIN_AGE_SECONDS = config(
    "FINIK_RECONCILIATION_MIN_AGE_SECONDS",
    default=30,
    cast=int,
)
FINIK_RECONCILIATION_LOOKBACK_HOURS = config(
    "FINIK_RECONCILIATION_LOOKBACK_HOURS",
    default=72,
    cast=int,
)
FINIK_PAYMENT_URL_ALLOWED_HOSTS = config(
    "FINIK_PAYMENT_URL_ALLOWED_HOSTS",
    default="qr.finik,qr.finik.kg",
    cast=Csv(),
)
PAYMENT_EVENT_PAYLOAD_RETENTION_DAYS = config(
    "PAYMENT_EVENT_PAYLOAD_RETENTION_DAYS",
    default=365,
    cast=int,
)
PAYMENT_WEBHOOK_MAX_BODY_BYTES = config("PAYMENT_WEBHOOK_MAX_BODY_BYTES", default=131072, cast=int)

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)
SECURE_REDIRECT_EXEMPT = [r"^health(?:/|$)"]
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=not DEBUG, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=not DEBUG, cast=bool)
USE_X_FORWARDED_PROTO = config("USE_X_FORWARDED_PROTO", default=False, cast=bool)
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if USE_X_FORWARDED_PROTO
    else None
)
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False, cast=bool)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=False, cast=bool)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
CLIENT_IP_HEADER = config("CLIENT_IP_HEADER", default="")
CLIENT_IP_TRUSTED_HOPS = config("CLIENT_IP_TRUSTED_HOPS", default=1, cast=int)
PERMISSIONS_POLICY = config(
    "PERMISSIONS_POLICY",
    default="camera=(), microphone=(), geolocation=(), payment=(self)",
)
CONTENT_SECURITY_POLICY = config(
    "CONTENT_SECURITY_POLICY",
    default=(
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self'; "
        "img-src 'self' data: https:; media-src 'self' https:; font-src 'self' data:; "
        "connect-src 'self'; frame-src 'none'; manifest-src 'self'"
    ),
)

SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=config("SENTRY_ENVIRONMENT", default="production"),
        traces_sample_rate=config("SENTRY_TRACES_SAMPLE_RATE", default=0.05, cast=float),
        send_default_pii=False,
    )

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "loggers": {
        "payment": {
            "handlers": ["console"],
            "level": config("PAYMENT_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
}
