"""
Django settings for system project.

Generated by 'django-admin startproject' using Django 5.1.3.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv
import os

import dj_database_url

load_dotenv()
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent



# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY", '\x9aL\xba\x10\xe4\xdc\x10\x9e\xe1\xb6\xbe[\xa9OI\x8f')

# SECURITY WARNING: don't run with debug turned on in 
DEBUG = False

if DEBUG == False:
    print(os.getenv("DEBUG"))
    

    allowed_host = os.getenv("ALLOWED_HOSTS", default="").strip().split(",")
    ALLOWED_HOSTS = allowed_host[:-1]
    print(allowed_host)

    csrf_origins = os.getenv("CSRF_TRUSTED_ORIGINS", default="").strip().split(",")
    CSRF_TRUSTED_ORIGINS = csrf_origins[:-1]
    print(csrf_origins)

    cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", default="").strip().split(",")
    CORS_ALLOWED_ORIGINS = cors_origins[:-1]
    print(cors_origins)

    SECURE_SSL_REDIRECT=False

    SECURE_HSTS_INCLUDE_SUBDOMAINS=True

    SECURE_HSTS_SECONDS=30

    SESSION_COOKIE_SECURE=True

    CSRF_COOKIE_SECURE=True

    SECURE_HSTS_PRELOAD=True

    SECURE_BROWSER_XSS_FILTER=True

    X_FRAME_OPTIONS='DENY'

else:
    DEBUG = True
    print("/n/n/n",DEBUG,os.getenv("DEBUG"))

    ALLOWED_HOSTS = ["*"]

    CORS_ALLOW_ALL_ORIGINS = True
    #CORS_ALLOWED_ORIGINS = ["http://127.0.0.1:3000", "http://localhost:3000", "http://172.20.10.5:3000"]

    #CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:3000", "http://localhost:3000"]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    #'django.contrib.sites',

    "whitenoise.runserver_nostatic",

    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "rest_framework_simplejwt",
    'corsheaders',

    "bookshelf",
    "auth",
]



MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    'corsheaders.middleware.CorsMiddleware',
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


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

if os.getenv("DATABASE_URL"):
    print("/n/n postgres",os.getenv("DATABASE_URL"))
    DATABASES = {
       'default': dj_database_url.config(default=os.getenv("DATABASE_URL"),
                                          conn_max_age=600,
                                          ssl_require=True,
                                          conn_health_checks=True)
    }
else:
    print("/n/n sqlite 3")
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = "static/"
MEDIA_URL = 'media/'

MEDIA_ROOT = BASE_DIR / "media"

if not DEBUG:
    STATIC_ROOT = os.path.join(BASE_DIR / 'staticfiles')
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

    MEDIA_ROOT = BASE_DIR / "mediafiles"

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": ['django_filters.rest_framework.DjangoFilterBackend'],

    'DEFAULT_PAGINATION_CLASS': "rest_framework.pagination.LimitOffsetPagination",
    'PAGE_SIZE': 50,

    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",

    'TEST_REQUEST_DEFAULT_FORMAT': 'json',

    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Safari PDF Reader',
    'DESCRIPTION': 'An api that serves the contents of pdf files so they can be read aloud',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

""" CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/0",
        #rediss://[[username]:[password]]@localhost:6379/0
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        'KEY_PREFIX': 'drf_cache'
    }
}
CACHE_TTL = 60 * 15 

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default" """

