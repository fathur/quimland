"""
Management command: list_early_payers

Lists residents who have fully settled *all* their routine (iuran) dues for a
given month on or before the payment grace day (PAYMENT_GRACE_DAY, currently the
5th). "Fully settled" is decided the same way the Leaderboard does it: for every
routine fund the resident has a tariff for that month, the cumulative payments
must reach the expected amount, and the date it reached it must be <= the 5th
(payments made in an earlier month count as early → still qualify). A period
covered by a DueNote (waiver/skip) counts as satisfied.

Usage:
  poetry run python manage.py list_early_payers [--month=YYYY-MM]

  --month  Month to inspect (default: current month).
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ql.fee.admin.dashboards.data import (
    PAYMENT_GRACE_DAY,
    _period_completion_date,
    year_note_map,
    year_paid_map,
    year_tariff_map,
)
from ql.fee.models import Fund

User = get_user_model()


class Command(BaseCommand):
    help = (
        "List residents who fully paid their routine dues on or before day "
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

        get_tariff = year_tariff_map(month_date.year)
        paid       = year_paid_map(month_date.year)
        notes      = year_note_map(month_date.year)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Residents fully paid on/before {cutoff.isoformat()} for {period}'
        ))

        matched = 0
        for user in users:
            fund_status = []      # [(fund_name, completion_at | None, 'note')]
            has_due = False
            all_settled = True

            for fund in funds:
                expected = get_tariff(user.id, fund.id, month_date)
                if expected is None:
                    continue
                has_due = True

                if (user.id, fund.id, period) in notes:
                    fund_status.append((fund.name, None, 'note'))
                    continue

                data = paid.get((user.id, fund.id, period))
                entries = data['entries'] if data else []
                completion_at = _period_completion_date(entries, expected)

                if completion_at is not None and completion_at <= cutoff:
                    fund_status.append((fund.name, completion_at, 'paid'))
                else:
                    all_settled = False

            if not has_due or not all_settled:
                continue

            matched += 1
            prop = user.properties
            home = prop.home_number or 'no home #'
            name = user.get_full_name() or user.username
            self.stdout.write(f'  [{home}] {name} (user_id={user.id})')
            for fund_name, completion_at, kind in fund_status:
                if kind == 'note':
                    self.stdout.write(f'      {fund_name}: waived (DueNote)')
                else:
                    self.stdout.write(f'      {fund_name}: paid {completion_at.isoformat()}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'{matched} resident(s) fully paid for {period}.'))
