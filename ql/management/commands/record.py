"""
Management command: record
Records iuran payments for a resident, continuing from the last recorded payment.

Usage:
  poetry run python manage.py record <user_id> [--general=N] [--garbage=N]
                                     [--year=YEAR] [--creator=<id>]

  - N is the number of consecutive months to record, starting after the last payment.
  - If no previous payment exists, recording starts from January of --year.
  - --year defaults to the current year (used only as fallback start year).
  - --creator defaults to the first superuser, or the resident themselves if none.
  - Skips any period that already has a positive payment recorded.
  - Errors if no active tariff is found for a requested kind+period.

Examples:
  # Record 10 months of general and 3 months of garbage, continuing from last payment
  manage.py record 42 --general=10 --garbage=3
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.db import transaction
from django.utils import timezone

from ql.models import Payment, PaymentBatch, Tariff
from ql.management.commands.seed_system import get_or_create_system_user

User = get_user_model()


def last_paid_period(user, kind) -> tuple[int, int] | None:
    """Return (year, month) of the last positive payment, or None if none exists."""
    last = (
        Payment.objects
        .filter(batch__user=user, kind=kind, nominal__gt=0)
        .order_by('-period')
        .values_list('period', flat=True)
        .first()
    )
    if last:
        return int(last[:4]), int(last[5:7])
    return None


def next_months(start_year: int, start_month: int, count: int):
    """Yield (year, month) for `count` months starting after (start_year, start_month)."""
    year, month = start_year, start_month
    for _ in range(count):
        month += 1
        if month > 12:
            month = 1
            year += 1
        yield year, month


class Command(BaseCommand):
    help = 'Record iuran payment(s) for a resident, continuing from the last payment.'

    def add_arguments(self, parser):
        parser.add_argument('user_id', type=int,
                            help='PK of the resident paying.')
        parser.add_argument('--general', type=int, default=None,
                            help='Number of consecutive months to record for monthly iuran.')
        parser.add_argument('--garbage', type=int, default=None,
                            help='Number of consecutive months to record for garbage iuran.')
        parser.add_argument('--year', type=int, default=None,
                            help='Fallback start year when no prior payment exists '
                                 '(default: current year).')
        parser.add_argument('--creator', type=int, default=None,
                            help='PK of the staff member recording this '
                                 '(default: first superuser).')

    def handle(self, *_, **options):
        today = datetime.date.today()
        fallback_year = options['year'] or today.year

        general_count = options['general']
        garbage_count = options['garbage']

        if general_count is None and garbage_count is None:
            raise CommandError('Specify at least --general=N or --garbage=N.')

        try:
            user = User.objects.get(pk=options['user_id'])
        except User.DoesNotExist:
            raise CommandError(f"No user with id={options['user_id']}.")

        if options['creator']:
            try:
                creator = User.objects.get(pk=options['creator'])
            except User.DoesNotExist:
                raise CommandError(f"No user with id={options['creator']} for --creator.")
        else:
            creator, _ = get_or_create_system_user()

        # Build list of (kind, year, month) entries to attempt
        entries: list[tuple[str, int, int]] = []

        for kind, count in [
            (Payment.Kind.MONTHLY, general_count),
            (Payment.Kind.GARBAGE, garbage_count),
        ]:
            if count is None:
                continue
            if count <= 0:
                raise CommandError(f'Month count for {kind} must be a positive integer.')

            last = last_paid_period(user, kind)
            start_year, start_month = last if last else (fallback_year, 0)

            if not last:
                self.stdout.write(
                    self.style.WARNING(
                        f'  No prior {kind} payment found — starting from {fallback_year}-01.'
                    )
                )

            for year, month in next_months(start_year, start_month, count):
                entries.append((kind, year, month))

        to_create: list[dict] = []

        for kind, year, month in entries:
            period_date = datetime.date(year, month, 1)
            period = f'{year:04d}-{month:02d}'

            tariff = (
                Tariff.objects
                .filter(
                    user=user,
                    kind=kind,
                    start_from__lte=period_date,
                )
                .filter(Q(end_to__isnull=True) | Q(end_to__gte=period_date))
                .order_by('-start_from')
                .first()
            )

            if tariff is None:
                raise CommandError(
                    f'No active {kind} tariff for "{user.username}" in {period}. '
                    f'Create a Tariff row first.'
                )

            already_paid = Payment.objects.filter(
                batch__user=user,
                kind=kind,
                period=period,
                nominal__gt=0,
            ).exists()

            if already_paid:
                self.stdout.write(
                    self.style.WARNING(
                        f'  SKIP  {kind:8s} {period}  — already recorded for {user.username}'
                    )
                )
                continue

            to_create.append({'kind': kind, 'period': period, 'nominal': tariff.nominal})

        if not to_create:
            self.stdout.write(self.style.WARNING('Nothing new to record.'))
            return

        with transaction.atomic():
            batch = PaymentBatch.objects.create(
                user=user,
                paid_at=timezone.now(),
                creator=creator,
                note='Recorded via `manage.py record`.',
            )
            for row in to_create:
                Payment.objects.create(
                    batch=batch,
                    kind=row['kind'],
                    period=row['period'],
                    nominal=row['nominal'],
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  OK    {row["kind"]:8s} {row["period"]}  '
                        f'Rp {row["nominal"]:>12,}  → {user.username}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Batch #{batch.pk} created (paid_at {batch.paid_at:%Y-%m-%d %H:%M %Z}).'
            )
        )
