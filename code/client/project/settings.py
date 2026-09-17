import os
import environ

from django.core.exceptions import ImproperlyConfigured


PROJECT_DIR = os.path.dirname(__file__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# -------------------- Local secrets (.env) --------------------
# Django's SECRET_KEY and the PUC cluster SSH credentials used by
# backend/utils.py's upload_parms() used to be hardcoded in source. They now
# live in code/client/.env instead, which .gitignore already excludes (see
# the repo-root .gitignore's bare ".env" entry -- matches at any depth).
# django-environ populates os.environ from that file if it exists, so both
# this module (via env(...)) and backend/utils.py (via os.environ.get(...))
# can read the same values. See .env.example for the keys this file expects
# and to regenerate it.
env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# -------------------- Optimizer solver configuration --------------------
# optimization_cpsat.py (the default and only in-request backend, OR-Tools
# CP-SAT) lives in backend/ and imports its own local model_common.py,
# right next to it -- code/server (the Gurobi backend that runs standalone
# on the cluster, reached only by SSH job submission -- see
# backend/utils.py's upload_parms()) is a separate, independently deployed
# project this one never imports from. See model_common.py's module
# docstring for why that copy is duplicated by hand rather than shared.

# Problems at or below this many *estimated decision variables* (see
# model_common.estimate_variable_count()) are solved synchronously inside
# the web request and the result is shown in the UI immediately. Bigger
# ones are handed off to the cluster as before, with results emailed later
# once done. SYNC_SOLVE_TMAX_SECONDS bounds how long the synchronous solve
# is allowed to run -- keep it well under your web server's request
# timeout (e.g. API Gateway / Lambda hard-caps a request at 29s).
#
# frontend/src/containers/CreateGroups.js shows a "this will run sync/async"
# indicator on the Configure & run screen based on this same number -- it
# reads it from window.__MATE_CONFIG__ (injected into index.html by
# frontend/views.py's index(), which passes this exact setting as template
# context) rather than hardcoding its own copy, so there's nothing to keep
# in sync by hand here: changing SYNC_SOLVE_MAX_VARIABLES (or
# MATE_SYNC_MAX_VARIABLES) changes what the UI shows too, automatically, on
# the next page load -- no frontend rebuild required.
#
# This used to be a raw student-count cap (SYNC_SOLVE_MAX_STUDENTS,
# default 100) -- replaced because student count alone is a poor proxy for
# how hard a roster actually is to solve: the same headcount can collapse
# into very different numbers of distinct student types, topics, and
# sections, which is what actually drives the model's size and solve time.
# 4000 is a measured, not a guessed, number -- see docs/ARCHITECTURE.md's
# note on this threshold: a 14-point benchmark correlating CP-SAT's own
# reported variable count against real solve time (production solver
# settings, greedy hint applied) found solves reliably finishing well
# inside a 30-60s budget up to a few thousand variables, with solve time
# climbing sharply beyond that. Bump this only after re-benchmarking
# against your actual configured Lambda memory/CPU and roster complexity.
SYNC_SOLVE_MAX_VARIABLES = int(os.environ.get("MATE_SYNC_MAX_VARIABLES", 4000))
SYNC_SOLVE_TMAX_SECONDS = int(os.environ.get("MATE_SYNC_TMAX_SECONDS", 20))

# The person running a sync solve can now choose their own time budget (see
# the slider on the Configure & run screen, CreateGroups.js) instead of
# always getting the fixed SYNC_SOLVE_TMAX_SECONDS above -- that setting is
# now just the *default* the slider starts at. Whatever the client sends is
# clamped server-side to [SYNC_SOLVE_TMAX_MIN_SECONDS,
# SYNC_SOLVE_TMAX_MAX_SECONDS] before it's ever handed to the solver (see
# views.run_model()), so a tampered or stale client can't ask for more time
# than this deployment allows -- the ceiling still has to leave margin under
# the same API Gateway / Lambda 29s hard cap SYNC_SOLVE_TMAX_SECONDS's own
# comment above describes.
SYNC_SOLVE_TMAX_MIN_SECONDS = int(os.environ.get("MATE_SYNC_TMAX_MIN_SECONDS", 5))
SYNC_SOLVE_TMAX_MAX_SECONDS = int(os.environ.get("MATE_SYNC_TMAX_MAX_SECONDS", 25))

# -------------------- Cluster access gate (Microsoft sign-in) --------------------
# The sync/CP-SAT path above is open to anyone -- it's free, open-source,
# and runs on this app's own Lambda. The *cluster* path (backend/views.py's
# large-roster branch, upload_parms()) spends a shared, licensed resource
# (the PUC cluster's Gurobi seat and compute), so it's gated behind sign-in
# with a uc.cl/ing.puc.cl account. See backend/msft_auth.py's module
# docstring for what this needs on the Azure side (an app registration --
# can't be done from here) and why the domain check happens here at the
# application level rather than via Azure tenant restriction.
MATE_ALLOWED_EMAIL_DOMAINS = os.environ.get("MATE_ALLOWED_EMAIL_DOMAINS", "uc.cl,ing.puc.cl")
MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET")
MS_AUTHORITY = os.environ.get("MS_AUTHORITY", "https://login.microsoftonline.com/organizations")
# Must exactly match a Redirect URI registered on the Azure app (OAuth
# redirect URIs are matched literally, not by prefix) -- register both this
# local-dev default and your deployed .../dev/auth/callback URL there, and
# set this env var per-environment (local .env vs. Lambda env vars) to
# whichever one applies. See README's Environment variables section.
MS_REDIRECT_URI = os.environ.get("MS_REDIRECT_URI", "http://localhost:8000/dev/auth/callback")

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
# routes under '/dev/' (matching the frontend's hardcoded axios paths) when
# DEBUG is True -- in the deployed Lambda "dev" stage that same prefix comes
# from the API Gateway stage name instead, so that deployment should set
# DJANGO_DEBUG=0 explicitly if it relies on the DEBUG=False branch.
DEBUG = os.environ.get("DJANGO_DEBUG", "1") not in ("0", "false", "False", "")

# The placeholder above is fine for local dev (DEBUG=True, see README's
# "Running locally") but must never be the *real* key -- SESSION_ENGINE is
# signed_cookies (no server-side session store), so SECRET_KEY is what
# actually stops someone from forging a session claiming an allowed uc.cl
# email (see backend/msft_auth.py's session_email_allowed()). Fail loudly at
# import time rather than silently running production on a public, well-known
# key.
_DEFAULT_SECRET_KEY = "django-insecure-change-me-see-env-example"
if not DEBUG and SECRET_KEY == _DEFAULT_SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is not set (still using the local-dev placeholder) "
        "while DJANGO_DEBUG=0. Set a real, unique DJANGO_SECRET_KEY in the "
        "environment/.env before running with DEBUG off -- see .env.example."
    )

# Comma-separated, same pattern as MATE_ALLOWED_EMAIL_DOMAINS above -- falls
# back to the previously-hardcoded list (local dev hosts plus this
# deployment's API Gateway hostname) so nothing breaks where the env var
# isn't set yet.
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
