import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

# Read CELERY_* settings from Django's settings.py.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks.py in each installed app.
app.autodiscover_tasks()
