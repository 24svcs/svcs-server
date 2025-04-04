from .common import *
from urllib.parse import urlparse
from decouple import config
import os

TIME_ZONE = 'UTC'

SECRET_KEY = config('SECRET_KEY')

DEBUG = True

tmpPostgres = urlparse(os.getenv("DATABASE_URL"))


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': tmpPostgres.path.replace('/', ''),
        'USER': tmpPostgres.username,
        'PASSWORD': tmpPostgres.password,
        'HOST': tmpPostgres.hostname,
        'PORT': 5432,
        'TEST': {
            'NAME': 'test_neondb_unique'
        }
    },
}


ALLOWED_HOSTS = [
    'localhost:8000',
    '127.0.0.1',
    '24svcs-server.up.railway.app',
    'http://127.0.0.1:8000/',
    'https://svcs-attendance-tracker.vercel.app',
    '.vercel.app',
    '.railway.app',
    'attendance.24svcs.com'
    
]

INTERNAL_IPS = [
    "127.0.0.1",
]


CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]


CSRF_TRUSTED_ORGINS = [
    'https://24svcs-server.up.railway.app',
    'https://svcs-attendance-tracker.vercel.app'
    '.vercel.app',
    '.railway.app',
    'https://attendance.24svcs.com',
    'localhost:8000/'
    ]
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True



LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',   
            'formatter': 'verbose'
        },
        'file': {
            'class': 'logging.FileHandler',
            'level': 'INFO',   
            'formatter': 'verbose',
            'filename': 'debug.log'
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',   
            'propagate': True,
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',   
    },     
    'formatters': {
        'verbose': {
            'format': '{asctime}( {levelname}) - {message}',
            'style': '{',
        },
    },
}