import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ql.models import UserProperty


class Command(BaseCommand):
    help = 'Create a new user with their UserProperty record.'

    def add_arguments(self, parser):
        parser.add_argument('--full-name',   required=True, help='Full name, e.g. "Budi Santoso"')
        parser.add_argument('--username',                   help='Login username (default: derived from full name)')
        parser.add_argument('--password',    default=None,  help='Initial password (omit to create account with no login access)')
        parser.add_argument('--home-number', default='',    help='House number, e.g. "12A"')
        parser.add_argument('--phone',       default='',    help='Phone number with country code, e.g. "+628123456789"')
        parser.add_argument(
            '--occupation',
            default='OCCUPIED',
            choices=['OCCUPIED', 'VACANT', 'RENT'],
            help='Occupancy status (default: OCCUPIED)',
        )

    def handle(self, *args, **options):
        User = get_user_model()

        full_name = options['full_name'].strip()
        parts = full_name.split(None, 1)
        first_name = parts[0]
        last_name  = parts[1] if len(parts) > 1 else ''

        username = options['username']
        if not username:
            username = re.sub(r'\s+', '_', full_name.lower())
            username = re.sub(r'[^a-z0-9_]', '', username)

        if User.objects.filter(username=username).exists():
            raise CommandError(f'Username "{username}" is already taken. Pass --username to choose another.')

        user = User.objects.create_user(
            username=username,
            password=options['password'],  # None → unusable password (no login until set)
            first_name=first_name,
            last_name=last_name,
        )

        UserProperty.objects.create(
            user=user,
            occupancy_status=options['occupation'],
            home_number=options['home_number'],
            phone=options['phone'],
        )

        self.stdout.write(self.style.SUCCESS(
            f'Created user "{username}" ({full_name})'
            + (f', home {options["home_number"]}' if options['home_number'] else '')
            + (f', phone {options["phone"]}' if options['phone'] else '')
            + f', {options["occupation"]}'
        ))
