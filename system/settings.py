"""
Django settings for the Bookverse system project.

Bookverse is an audiobook-style document reader: a single ASGI process
(Gunicorn + UvicornWorker) serves both the DRF HTTP API and the Channels
WebSocket audio stream. Object storage is S3-compatible (MinIO on the VPS).
"""

from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable robustly.

    ``os.getenv`` returns strings, so ``DEBUG=False`` in the environment is the
    truthy string ``"False"``. This collapses the common truthy spellings.
    """
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    """Comma-separated env var -> clean list (no empty trailing entries)."""
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Core security
# ---------------------------------------------------------------------------
DEBUG = env_bool("DEBUG", True)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        # Ephemeral, dev-only key. Never used when DEBUG is off.
        SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY environment variable must be set when DEBUG is off."
        )

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "bookverse.api.ecode2.com")


# ---------------------------------------------------------------------------
# CORS / CSRF
#
# bookverse.ecode2.com (frontend) and bookverse.api.ecode2.com (this app)
# share the registrable domain ecode2.com -> same-site, cross-origin.
# ---------------------------------------------------------------------------
if DEBUG:
    CORS_ALLOWED_ORIGINS = env_list(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    CSRF_TRUSTED_ORIGINS = env_list(
        "CSRF_TRUSTED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
else:
    CORS_ALLOWED_ORIGINS = env_list(
        "CORS_ALLOWED_ORIGINS", "https://bookverse.ecode2.com"
    )
    CSRF_TRUSTED_ORIGINS = env_list(
        "CSRF_TRUSTED_ORIGINS", "https://bookverse.ecode2.com"
    )

CORS_ALLOW_CREDENTIALS = True


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Channels' Daphne integration must precede staticfiles.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",

    "whitenoise.runserver_nostatic",

    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "corsheaders",
    "storages",

    "bookshelf",
    "auth",
]


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "system.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "system.wsgi.application"
ASGI_APPLICATION = "system.asgi.application"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
if os.getenv("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(
            default=os.getenv("DATABASE_URL"),
            conn_max_age=600,
            ssl_require=not DEBUG and env_bool("DB_SSL_REQUIRE", True),
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ---------------------------------------------------------------------------
# Cache + Channel layer (Redis)
# ---------------------------------------------------------------------------
REDIS_CACHE_URL = os.getenv("CACHE_DB", "redis://127.0.0.1:6379/1")
REDIS_CHANNEL_URL = os.getenv("CHANNEL_DB", "redis://127.0.0.1:6379/2")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}
CACHE_TTL = 60 * 15

# channels_redis waits for messages with a *blocking* BZPOPMIN whose server-side
# timeout is `RedisChannelLayer.brpop_timeout` (5s). redis-py >= 6 changed the
# default client `socket_timeout` from None to 5s, so the socket read deadline
# and the blocking pop expire at the same moment: an idle WebSocket dies with
# "redis.exceptions.TimeoutError: Timeout reading from ...". The socket timeout
# must therefore stay comfortably above brpop_timeout.
CHANNELS_BRPOP_TIMEOUT = 5  # must match RedisChannelLayer.brpop_timeout
CHANNELS_SOCKET_TIMEOUT = CHANNELS_BRPOP_TIMEOUT * 4

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                {
                    "address": REDIS_CHANNEL_URL,
                    "socket_timeout": CHANNELS_SOCKET_TIMEOUT,
                    "socket_connect_timeout": 5,
                    "socket_keepalive": True,
                }
            ],
        },
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static + media (object storage)
#
# Static files are served by WhiteNoise. Media (uploaded books + synthesized
# audio) lives in S3-compatible storage (MinIO). If no bucket is configured we
# fall back to local filesystem so a bare checkout still runs.
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME")
USE_S3 = bool(AWS_STORAGE_BUCKET_NAME)

if USE_S3:
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL")  # e.g. http://127.0.0.1:9000
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "us-east-1")
    AWS_S3_USE_SSL = env_bool("AWS_S3_USE_SSL", not DEBUG)
    # MinIO requires path-style addressing (bucket in the path, not the host).
    AWS_S3_ADDRESSING_STYLE = os.getenv("AWS_S3_ADDRESSING_STYLE", "path")
    # Public, time-limited URL for media when a custom domain is configured.
    AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN") or None
    AWS_QUERYSTRING_AUTH = env_bool("AWS_QUERYSTRING_AUTH", True)
    AWS_QUERYSTRING_EXPIRE = int(os.getenv("AWS_QUERYSTRING_EXPIRE", str(60 * 60)))
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None

    STORAGES = {
        "default": {"BACKEND": "bookshelf.storage_backends.MediaStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }
else:
    MEDIA_URL = "media/"
    MEDIA_ROOT = os.path.join(BASE_DIR, "media")
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "1000/day",
        "anon": "100/day",
        "tts": "300/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Bookverse Reader API",
    "DESCRIPTION": "Audiobook-style document reader: TTS streaming, reading "
    "progress, bookmarks, and native audiobook playback.",
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}


# ---------------------------------------------------------------------------
# Auth cookies (hybrid scheme: in-memory access token + httpOnly refresh cookie)
# ---------------------------------------------------------------------------
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None  # e.g. ".ecode2.com"
REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "bv_refresh")
REFRESH_COOKIE_SECURE = env_bool("REFRESH_COOKIE_SECURE", not DEBUG)
REFRESH_COOKIE_SAMESITE = os.getenv("REFRESH_COOKIE_SAMESITE", "Lax")

# Local development is served over plain HTTP from localhost/127.0.0.1, where
# production cookie flags make the refresh cookie *impossible to store*:
#   - Domain=.example.com does not match the request host, so the browser
#     discards the cookie outright;
#   - Secure cookies are never stored over http://.
# Since .env is normally copied from the production template, silently honouring
# those values means every full page reload logs the developer out with no error
# anywhere. Override them in DEBUG rather than require a hand-edited .env.
if DEBUG:
    if COOKIE_DOMAIN and not COOKIE_DOMAIN.lstrip(".").startswith(("localhost", "127.0.0.1")):
        import warnings

        warnings.warn(
            f"DEBUG: ignoring COOKIE_DOMAIN={COOKIE_DOMAIN!r} -- the browser "
            "would reject a cookie scoped to that domain when served from "
            "localhost, so the refresh cookie would never be stored.",
            stacklevel=1,
        )
        COOKIE_DOMAIN = None
    if REFRESH_COOKIE_SECURE:
        import warnings

        warnings.warn(
            "DEBUG: forcing REFRESH_COOKIE_SECURE=False -- a Secure cookie is "
            "not stored over plain HTTP, which silently breaks session refresh.",
            stacklevel=1,
        )
        REFRESH_COOKIE_SECURE = False

# Short-lived signed ticket used to authenticate the audio WebSocket.
WS_TICKET_TTL_SECONDS = int(os.getenv("WS_TICKET_TTL_SECONDS", "30"))


# ---------------------------------------------------------------------------
# Text-to-Speech (pluggable provider)
# ---------------------------------------------------------------------------
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "nvidia")  # "nvidia" | "google" | "piper" | "dummy"
TTS_DEFAULT_VOICE = os.getenv("TTS_DEFAULT_VOICE", "Magpie-Multilingual.EN-US.Aria")
TTS_DEFAULT_LANGUAGE = os.getenv("TTS_DEFAULT_LANGUAGE", "en-US")
# Container delivered to the browser. MP3 is the safe default: it is the one
# lossy format every target browser (notably iOS Safari) decodes reliably via
# decodeAudioData(). Providers returning raw PCM compress to this.
TTS_AUDIO_ENCODING = os.getenv("TTS_AUDIO_ENCODING", "MP3")  # MP3 | OGG_OPUS | AAC | WAV
# ~48 kbps mono is transparent for speech and ~15x smaller than raw WAV.
TTS_AUDIO_BITRATE = os.getenv("TTS_AUDIO_BITRATE", "48k")
TTS_MAX_INPUT_BYTES = int(os.getenv("TTS_MAX_INPUT_BYTES", "4500"))
# NVIDIA Riva engine config (only used when TTS_PROVIDER=nvidia). NVIDIA's
# hosted TTS models are served over gRPC and selected by a "function-id"
# (copy it from the model's page on build.nvidia.com), not a model name --
# the default below is Magpie-TTS Multilingual.
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_TTS_SERVER = os.getenv("NVIDIA_TTS_SERVER", "grpc.nvcf.nvidia.com:443")
NVIDIA_TTS_FUNCTION_ID = os.getenv(
    "NVIDIA_TTS_FUNCTION_ID", "877104f7-e885-42b9-8de8-f6e4c6303969"
)
NVIDIA_TTS_USE_SSL = os.getenv(
    "NVIDIA_TTS_USE_SSL", "true" if NVIDIA_TTS_SERVER == "grpc.nvcf.nvidia.com:443" else "false"
).lower() == "true"
NVIDIA_TTS_SAMPLE_RATE_HZ = int(os.getenv("NVIDIA_TTS_SAMPLE_RATE_HZ", "44100"))
# Local engine config (only used when TTS_PROVIDER=piper).
PIPER_BINARY = os.getenv("PIPER_BINARY", "piper")
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", "")
# Budget (bytes) for the synthesized-audio cache eviction command.
AUDIO_CACHE_MAX_BYTES = int(os.getenv("AUDIO_CACHE_MAX_BYTES", str(2 * 1024**3)))

# Default language for new books / parsing.
DEFAULT_BOOK_LANGUAGE = os.getenv("DEFAULT_BOOK_LANGUAGE", "en-US")
