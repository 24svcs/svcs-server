from pathlib import Path
import os
from celery.schedules import crontab
BASE_DIR = Path(__file__).resolve().parent.parent
from decouple import config


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'debug_toolbar',
    'core',
    'rest_framework',
    'guardian',
    'django_filters',
    'phonenumber_field',
    'api',
    'organization',
    'human_resources',
    'finance',
    'django_moncash',
    'django_countries'
]

MIDDLEWARE = [
   'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware'
]

ROOT_URLCONF = 'svcs.urls'

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
APPEND_SLASH=False
WSGI_APPLICATION = 'svcs.wsgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'core.User'



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


AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',
)

REST_FRAMEWORK = {
    'COERCE_DECIMAL_TO_STRING': False,
    'EXCEPTION_HANDLER': 'api.libs.error_handler.custom_error_handler',
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "core.authentication.ClerkAuthentication",
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'api.throttling.BurstRateThrottle',
        'api.throttling.SustainedRateThrottle',
        'api.throttling.AnonymousRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'burst': '60/min',
        'sustained': '1000/day',
        'anon': '20/hour',
    }
}

LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_URL = '/media/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')



CLERK_FRONTEND_API_URL = config('CLERK_FRONTEND_API_URL')
CLERK_SECRET_KEY = config('CLERK_SECRET_KEY')
CLERK_JWKS_URL = config('CLERK_JWKS_URL')
CLERK_ISSUER = config('CLERK_ISSUER')
CLERK_AUDIENCE= config('CLERK_AUDIENCE')
CLERK_JWKS_CACHE_KEY = config('CLERK_JWKS_CACHE_KEY')
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True



CELERY_BROKER_URL = config('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND')


EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
RESEND_SMTP_PORT = 587
RESEND_SMTP_USERNAME = 'resend'
RESEND_SMTP_HOST = 'smtp.resend.com'
RESEND_API_KEY = config('RESEND_API_KEY')


MONCASH = {
        'CLIENT_ID':'YOUR_CLIENT_ID',
        'SECRET_KEY':'YOUR_SECRET_KEY',
        'ENVIRONMENT':'sandbox or production'
    }

CELERY_BEAT_SCHEDULE = {
    'generate_attendance_reports': {
        },
    'generate_attendance_reports': {
        'task': 'api.jobs.generate_attendance_report.generate_attendance_reports',
        'schedule': crontab(hour='*/1'),
        'args': ()
    },
    'refine_attendance_records': {
        'task': 'api.jobs.refine_attendance_record.refine_attendance_records',
        'schedule': crontab(day_of_week=0),
    },
    'generate_recurring_invoices': {
        'task': 'api.jobs.generate_invoices.generate_recurring_invoices',
        'schedule': crontab(hour=0, minute=0),  # Run daily at midnight
        'args': ()
    }
}
