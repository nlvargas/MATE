import os
import environ

from django.core.exceptions import ImproperlyConfigured


PROJECT_DIR = os.path.dirname(__file__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# -------------------- Local secrets (.env) --------------------
# Secrets (SECRET_KEY, cluster SSH creds) live in code/client/.env, gitignored,
# not hardcoded. django-environ loads it into os.environ, so both env(...)
# here and os.environ.get(...) in backend/utils.py read the same values.
# See .env.example for the expected keys.
env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# -------------------- Optimizer solver configuration --------------------
# optimization_cpsat.py (OR-Tools CP-SAT, the only in-request backend) lives
# in backend/ with its own local model_common.py. code/cluster (Gurobi, on
# the cluster, reached only via SSH job submission -- backend/utils.py's
# upload_parms()) is a separate project this one never imports from.

# Rosters at or below this many *estimated decision variables* (see
# model_common.estimate_variable_count()) solve synchronously in the web
# request; bigger ones are rejected as too large for this deployment (see
# views.run_model()) -- there's no cluster hand-off anymore.
# SYNC_SOLVE_TMAX_SECONDS bounds the synchronous solve -- keep it under your
# server's request timeout (Lambda/API Gateway hard-caps a request at 29s).
# frontend/src/containers/CreateGroups.js reads this same number via
# window.__MATE_CONFIG__ (injected by frontend/views.py's index()) so
# there's nothing to keep in sync by hand.
# 15000 covers the production-sized roster used to validate this change (809
# students, 4 attributes, 10 topics, ~14,500 estimated variables, solved to
# proven optimality in ~8s on a 4-core machine) -- see docs/TECHNICAL_OVERVIEW.md's
# note on the threshold. The estimate counts variables, not difficulty: a
# roster with many distinct student types can be much harder than one with
# few at the same count, so re-measure on your actual Lambda memory/CPU
# before relying on it, and lower it via MATE_SYNC_MAX_VARIABLES if solves
# start missing the time budget.
SYNC_SOLVE_MAX_VARIABLES = int(os.environ.get("MATE_SYNC_MAX_VARIABLES", 15000))
SYNC_SOLVE_TMAX_SECONDS = int(os.environ.get("MATE_SYNC_TMAX_SECONDS", 20))

# The Configure & run screen's slider lets the user pick their own time
# budget instead of always using SYNC_SOLVE_TMAX_SECONDS (now just the
# slider's default). views.run_model() clamps whatever the client sends to
# [SYNC_SOLVE_TMAX_MIN_SECONDS, SYNC_SOLVE_TMAX_MAX_SECONDS] before handing
# it to the solver, so a tampered/stale client can't exceed this deployment's
# cap -- the ceiling still needs margin under the 29s limit noted above.
SYNC_SOLVE_TMAX_MIN_SECONDS = int(os.environ.get("MATE_SYNC_TMAX_MIN_SECONDS", 5))
SYNC_SOLVE_TMAX_MAX_SECONDS = int(os.environ.get("MATE_SYNC_TMAX_MAX_SECONDS", 25))


# django.contrib.sessions defaults to DB-backed sessions, which can't work
# here -- DATABASES = {} below, there's no database at all. Signed, itself-
# contained cookies need nothing server-side; the only things ever stored
# in a session are a short-lived MSAL auth-flow dict (during sign-in) and,
# after a successful sign-in, the user's verified email address -- both
# small enough to fit comfortably in a cookie.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret! Pulled
# from .env (DJANGO_SECRET_KEY) -- the fallback below is only ever used if
# that file is missing, so a fresh clone doesn't hard-fail on import; it is
# NOT the real key and shouldn't be relied on past local, throwaway use.
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-change-me-see-env-example")

# DJANGO_DEBUG unset (or any value other than "0"/"false") => DEBUG=True.
# Local `runserver` needs DEBUG=True: project/urls.py only mounts backend
# routes under '/dev/' when DEBUG is True. The frontend learns that prefix
# from frontend/views.py's _api_base() (window.__MATE_CONFIG__.apiBase), so
# the deployed Lambda should set DJANGO_DEBUG=0: its routes then live at the
# root of the custom domain, and at the stage name on the execute-api URL.
DEBUG = os.environ.get("DJANGO_DEBUG", "1") not in ("0", "false", "False", "")

# Fine as a placeholder for local dev, but must never be the *real* key --
# SESSION_ENGINE is signed_cookies (no server-side session store), so
# SECRET_KEY is what stops someone forging or tampering with a session
# cookie's contents. Fail loudly at import time rather than silently
# running on a public key.
_DEFAULT_SECRET_KEY = "django-insecure-change-me-see-env-example"
if not DEBUG and SECRET_KEY == _DEFAULT_SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is not set (still using the local-dev placeholder) "
        "while DJANGO_DEBUG=0. Set a real, unique DJANGO_SECRET_KEY in the "
        "environment/.env before running with DEBUG off -- see .env.example."
    )

# Comma-separated -- falls back to the previously-hardcoded list (local dev
# hosts plus this deployment's API Gateway hostname) so nothing breaks
# where the env var isn't set yet.
MATE_ALLOWED_HOST = os.environ.get(
    "MATE_ALLOWED_HOST",
    "127.0.0.1,0.0.0.0,localhost,my49ptyg5m.execute-api.us-east-2.amazonaws.com",
)
ALLOWED_HOSTS = [h.strip() for h in MATE_ALLOWED_HOST.split(",") if h.strip()]

if DEBUG:
    STATIC_URL = '/static/'
else:
    S3_BUCKET_NAME = "mate-static-files"
    AWS_S3_BUCKET_NAME_STATIC = S3_BUCKET_NAME
    AWS_S3_CUSTOM_DOMAIN = f'{S3_BUCKET_NAME}.s3.amazonaws.com'
    STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
    # if you have configured a custom domain for your static files use:
    #AWS_S3_PUBLIC_URL_STATIC = "https://static.yourdomain.com/"

# STATICFILES_STORAGE was removed in Django 5.1 in favor of this STORAGES
# dict (deprecated since 4.2). django_s3_storage's backend classes are plain
# Storage subclasses, so they drop straight into the new "staticfiles" slot.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG else
            "django_s3_storage.storage.StaticS3Storage"
        ),
    },
}

STATIC_ROOT = os.path.join(BASE_DIR, 'static/')

# Django 5.2+ system-check default; no DB is configured (DATABASES = {}) so
# this mostly silences the W042 warning from the built-in auth/admin apps.
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'backend.apps.BackendConfig',
    'rest_framework',
    'rest_framework.authtoken',
    'frontend',
    'django_s3_storage',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

DATABASES = {}


# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

#Auth settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
}


# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

# USE_L10N was removed as a Django setting in 5.0 (localized formatting is
# always on now); the line used to be here and is just dead weight in 5.2+.

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/
# NOTE: STATIC_URL/STATIC_ROOT are already set above (lines 71-79, 97) based
# on DEBUG -- this used to unconditionally reset STATIC_URL to '/static/'
# here, silently overwriting the S3 CDN URL in production. Removed; do not
# reintroduce a bare STATIC_URL assignment below this comment.

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media/')

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'django.contrib.staticfiles.finders.FileSystemFinder',
)

STATICFILES_DIR = [
    os.path.join(BASE_DIR, 'staticfiles'),
]


CORS_REPLACE_HTTPS_REFERER      = False
HOST_SCHEME                     = "http://"
# SECURE_PROXY_SSL_HEADER         = None
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT             = False
SESSION_COOKIE_SECURE           = not DEBUG
CSRF_COOKIE_SECURE              = not DEBUG
SECURE_HSTS_SECONDS             = None
SECURE_HSTS_INCLUDE_SUBDOMAINS  = False
SECURE_FRAME_DENY               = False
