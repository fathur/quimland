"""
Management command: sent_login

For every resident who fully settled *all* their routine (iuran) dues for a given
month on or before the payment grace day (PAYMENT_GRACE_DAY, currently the 5th),
this command:

  1. Generates a fresh random password and sets it on the user account.
  2. Creates a messaging.Message addressed to that user containing their Portal
     Warga login details.

"Fully settled" is decided the same way the Leaderboard does it: for every
routine fund the resident has a tariff for that month, cumulative payments must
reach the expected amount and the completion date must be <= the 5th (payments
made in an earlier month count as early → still qualify). A period covered by a
DueNote (waiver/skip) counts as satisfied.

Residents who already have a Message, or who are already staff (login was
activated before), are skipped and listed on the console, so the command is safe
to re-run. Residents with no phone number on their UserProperty are also skipped.
Newly activated users are made staff and added to groups 1-4.

Usage:
  poetry run python manage.py sent_login [--month=YYYY-MM]

  --month  Month to inspect (default: current month).
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from ql.fee.admin.dashboards.data import (
    PAYMENT_GRACE_DAY,
    _period_completion_date,
    year_note_map,
    year_paid_map,
    year_tariff_map,
)
from ql.fee.models import Fund
from ql.messaging.models import Message

User = get_user_model()

# Unambiguous alphabet — no 0/O/1/l/I — so the password is easy to read/type
# off a chat message.
PASSWORD_ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
PASSWORD_LENGTH = 10

# Groups every newly activated resident is added to (hardcoded by request).
ACTIVATION_GROUP_IDS = [2, 4]

MESSAGE_TEMPLATE = (
    "Bapak {name}, selamat malam \U0001f64f\n"
    "\n"
    "Karena sudah bayar iuran sebelum tanggal 5, akses Portal Warga untuk "
    "Bapak/Ibu sudah kami aktifkan (ini termasuk warga prioritas tahap 2).\n"
    "\n"
    "Berikut infonya:\n"
    "\U0001f517 Portal: https://warga.quimland.com\n"
    "\U0001f4f1 Username: {username} or {phone}\n"
    "\U0001f511 Password: {password}\n"
    "\n"
    "Segera update password setelah login pertama kali, ya. Jangan lupa catat password baru Bapak/Ibu.\n"
    "Untuk warga lain, akses akan menyusul bertahap (tahap 3, 4, dst) dalam "
    "waktu dekat.\n"
    "\n"
    "Kalau ada kendala login, langsung chat aja ke sini. Terima kasih \U0001f64f"
)


class Command(BaseCommand):
    help = (
        "Reset the password and create a Portal Warga login Message for every "
        f"resident who fully paid their routine dues on or before day "
        f"{PAYMENT_GRACE_DAY} of the given month (default: current month)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--month', default=None,
            help='Month to inspect as YYYY-MM (default: current month).',
        )

    def _parse_month(self, value):
        if not value:
            today = timezone.localdate()
            return date(today.year, today.month, 1)
        try:
            year, month = int(value[:4]), int(value[5:7])
            return date(year, month, 1)
        except (ValueError, IndexError):
            raise CommandError(f'Invalid --month {value!r}; expected YYYY-MM.')

    def handle(self, *args, **options):
        month_date = self._parse_month(options['month'])
        period = month_date.strftime('%Y-%m')
        cutoff = date(month_date.year, month_date.month, PAYMENT_GRACE_DAY)

        funds = list(Fund.objects.filter(kind=Fund.Kind.ROUTINE).order_by('name'))
        if not funds:
            raise CommandError('No routine funds configured.')

        users = list(
            User.objects
            .filter(is_active=True, properties__isnull=False)
            .select_related('properties')
            .order_by('properties__home_number', 'username')
        )

        already_messaged = set(
            Message.objects.values_list('recipient_id', flat=True)
        )

        get_tariff = year_tariff_map(month_date.year)
        paid       = year_paid_map(month_date.year)
        notes      = year_note_map(month_date.year)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Portal Warga login messages for residents fully paid on/before '
            f'{cutoff.isoformat()} ({period})'
        ))

        created = 0
        skipped_existing = 0
        skipped_staff = 0
        skipped_no_phone = 0
        for user in users:
            has_due = False
            all_settled = True

            for fund in funds:
                expected = get_tariff(user.id, fund.id, month_date)
                if expected is None:
                    continue
                has_due = True

                if (user.id, fund.id, period) in notes:
                    continue

                data = paid.get((user.id, fund.id, period))
                entries = data['entries'] if data else []
                completion_at = _period_completion_date(entries, expected)

                if not (completion_at is not None and completion_at <= cutoff):
                    all_settled = False
                    break

            if not has_due or not all_settled:
                continue

            if user.id in already_messaged:
                skipped_existing += 1
                self.stdout.write(f'  - {user.username}: already has a Message, skipped')
                continue

            if user.is_staff:
                skipped_staff += 1
                self.stdout.write(self.style.WARNING(
                    f'  - {user.username}: already staff, skipped'
                ))
                continue

            if not (user.properties.phone or '').strip():
                skipped_no_phone += 1
                self.stdout.write(self.style.WARNING(
                    f'  - {user.username}: no phone number in user property, skipped'
                ))
                continue

            name = user.get_full_name() or user.username
            password = get_random_string(PASSWORD_LENGTH, PASSWORD_ALPHABET)
            content = MESSAGE_TEMPLATE.format(
                name=name, username=user.username, password=password, phone=user.properties.phone
            )

            with transaction.atomic():
                user.set_password(password)
                user.is_staff = True
                user.save(update_fields=['password', 'is_staff'])
                user.groups.set(ACTIVATION_GROUP_IDS)
                Message.objects.create(recipient=user, content=content)

            created += 1
            self.stdout.write(self.style.SUCCESS(
                f'  + {user.username} ({name}): password reset, Message created'
            ))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'{created} Message(s) created; {skipped_existing} skipped (already messaged); '
            f'{skipped_staff} skipped (already staff); '
            f'{skipped_no_phone} skipped (no phone number).'
        ))
