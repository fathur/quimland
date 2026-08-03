from pathlib import Path
import os

from celery.schedules import crontab
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-yzw+hvukmv#7rq1$bw^a_*estnrtk&w439cg&5(2m8u@%#d9q_',
)

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

INTERNAL_IPS = [
    # ...
    "127.0.0.1",
    "localhost",
    # ...
]

# ---------------------------------------------------------------------------
# Debug toolbar — visibility is controlled by this flag + staff status
# (ql.services.utils.show_toolbar_to_staff), NOT by DEBUG. This lets the
# toolbar be switched on for staff on the production domain (quimland.com)
# without ever turning on DEBUG's verbose error pages for real residents.
# Off by default; flip only while actively debugging.
# ---------------------------------------------------------------------------
DEBUG_TOOLBAR_ENABLED = os.environ.get('DEBUG_TOOLBAR_ENABLED', 'False') == 'True'

DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': 'ql.services.utils.show_toolbar_to_staff',
}

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',') if os.environ.get('ALLOWED_HOSTS') else []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'admin_auto_filters',
    # 'mcp_server',
    'mptt',
    'ql',
    'sorl.thumbnail',
    'django_extensions',
    'rest_framework',
    'debug_toolbar',
    'django_celery_beat',
    'more_admin_filters'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    'debug_toolbar.middleware.DebugToolbarMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------------------------------------------------------
# Database — Postgres via env vars; falls back to SQLite for quick local dev
# ---------------------------------------------------------------------------
_db_engine = os.environ.get('DB_ENGINE', 'django.db.backends.postgresql')

if _db_engine == 'django.db.backends.sqlite3':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME':     os.environ.get('DB_NAME',     'quimland'),
            'USER':     os.environ.get('DB_USER',     'psql'),
            'PASSWORD': os.environ.get('DB_PASSWORD', 'passwd'),
            'HOST':     os.environ.get('DB_HOST',     'localhost'),
            'PORT':     os.environ.get('DB_PORT',     '5432'),
        }
    }

AUTHENTICATION_BACKENDS = [
    'ql.services.auth_backends.PhoneOrUsernameBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Jakarta'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = os.environ.get('STATIC_ROOT', str(BASE_DIR / 'staticfiles'))

MEDIA_URL = 'media/'
MEDIA_ROOT = os.environ.get('MEDIA_ROOT', str(BASE_DIR / 'media'))

# Receipts and other sensitive uploads — NOT under MEDIA_ROOT, NOT publicly served.
# Access is gated by the /secure-media/ view which enforces authentication.
SECURE_MEDIA_ROOT = os.environ.get('SECURE_MEDIA_ROOT', str(BASE_DIR / 'secure_media'))
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# File storage — set STORAGE_BACKEND=r2 in .env to route uploads to R2
# ---------------------------------------------------------------------------
STORAGE_BACKEND = os.environ.get('STORAGE_BACKEND', 'local')  # 'local' | 'r2'

R2_BUCKET_NAME      = os.environ.get('R2_BUCKET_NAME', '')
R2_ENDPOINT_URL     = os.environ.get('R2_ENDPOINT_URL', '')   # https://<account_id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID    = os.environ.get('R2_ACCESS_KEY_ID', '')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY', '')
R2_CUSTOM_DOMAIN    = os.environ.get('R2_CUSTOM_DOMAIN', '')  # optional public domain, e.g. cdn.example.com

# Max size (bytes) for a directly-uploaded Asset file. Larger files must be
# referenced by URL instead. Default: 10 MiB.
ASSET_MAX_UPLOAD_SIZE = int(os.environ.get('ASSET_MAX_UPLOAD_SIZE', 10 * 1024 * 1024))

# ---------------------------------------------------------------------------
# WhatsApp Business API (Meta Cloud API) webhook
# ---------------------------------------------------------------------------
WHATSAPP_VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', '')
WHATSAPP_APP_SECRET = os.environ.get('WHATSAPP_APP_SECRET', '')
WHATSAPP_PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '')
WHATSAPP_ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN', '')
WHATSAPP_API_VERSION = os.environ.get('WHATSAPP_API_VERSION', 'v21.0')

LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'whatsapp_file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': LOG_DIR / 'whatsapp.log',
            'when': 'midnight',
            'backupCount': 14,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'ql.views.whatsapp': {
            'handlers': ['whatsapp_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ---------------------------------------------------------------------------
# Celery — broker/result backend default to Redis on localhost; override via
# env for prod (e.g. a managed Redis URL). See config/celery.py for the app.
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# django_celery_beat stores the schedule in the DB (editable from /admin/ —
# Periodic Tasks, Crontabs, Intervals, etc.) instead of only here in code.
# Needs `celery -A config beat` running alongside the worker.
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Seed only: on first run, DatabaseScheduler copies entries from this dict
# into the DB (django_celery_beat_periodictask) if they don't already exist
# there, then ignores this dict — from then on, edit the schedule in /admin/.
CELERY_BEAT_SCHEDULE = {
    'sync-resident-admin-access-daily': {
        'task': 'ql.tasks.access_control.sync_resident_admin_access',
        'schedule': crontab(hour=1, minute=0),
    },
}
