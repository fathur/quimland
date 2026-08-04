"""
Management command: seed_system
Creates the built-in system user used as the default creator for automated actions.

Usage:
  poetry run python manage.py seed_system
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

SYSTEM_USERNAME = 'system'


def get_or_create_system_user():
    user, created = User.objects.get_or_create(
        username=SYSTEM_USERNAME,
        defaults=dict(
            first_name='System',
            last_name='',
            is_active=False,
            is_staff=False,
            is_superuser=False,
        ),
    )
    return user, created


class Command(BaseCommand):
    help = 'Create the built-in system user (idempotent).'

    def handle(self, *_, **__):
        _, created = get_or_create_system_user()
        if created:
            self.stdout.write(self.style.SUCCESS(f'System user "{SYSTEM_USERNAME}" created.'))
        else:
            self.stdout.write(f'System user "{SYSTEM_USERNAME}" already exists.')
