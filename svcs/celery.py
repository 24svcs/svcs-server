import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.prod')
celery = Celery('svcs')

celery.config_from_object('django.conf:settings', namespace='CELERY')
celery.autodiscover_tasks()