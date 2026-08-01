from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ql.admin.dashboards.data import (
    PAYMENT_GRACE_DAY,
    POINTS_EARLY_PERIOD,
    POINTS_LATE_PERIOD,
    POINTS_ONTIME_PERIOD,
    POINTS_PER_RUPIAH,
    _months_through,
    _period_completion_date,
    year_note_map,
    year_paid_map,
    year_tariff_map,
)
from ql.models import Fund, Transaction, TransactionItem
from ql.services.utils import fmt_rupiah


class Command(BaseCommand):
    help = (
        "Per-period breakdown of one resident's Leaderboard numbers: which routine "
        "periods counted as early/on-time/late/unpaid (and why), which transactions "
        "counted as other income, and which periods are outstanding. Reuses the same "
        "ql.admin.dashboards.data helpers as the Leaderboard page, so the totals "
        "printed here are guaranteed to match what's shown on screen."
    )

    def add_arguments(self, parser):
        parser.add_argument('user_id', type=int, help='auth_user.id of the resident to inspect')
        parser.add_argument(
            '--year', type=int, default=None,
            help='Year to inspect (default: current year, matching the Leaderboard page)',
        )

    def handle(self, *args, **options):
        try:
            user = User.objects.select_related('properties').get(pk=options['user_id'])
        except User.DoesNotExist:
            raise CommandError(f"No user with id={options['user_id']}")

        today = timezone.localdate()
        year = options['year'] or today.year

        funds  = list(Fund.objects.filter(kind=Fund.Kind.ROUTINE).order_by('name'))
        months = _months_through(year, today)

        get_tariff = year_tariff_map(year)
        paid       = year_paid_map(year)
        notes      = year_note_map(year)

        name = user.get_full_name() or user.username
        prop = getattr(user, 'properties', None)
        home = getattr(prop, 'home_number', '') if prop else ''

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Leaderboard detail — {name} ({home or "no home #"}) [user_id={user.id}] — year {year}'
        ))
        self.stdout.write(
            f'Grace day: paid on/before day {PAYMENT_GRACE_DAY} of the due month = on-time; '
            f'paid before the due month starts = early; later = late; still unpaid = outstanding.\n'
        )

        zero = Decimal('0')
        counts = {'early': 0, 'ontime': 0, 'late': 0, 'unpaid': 0}
        outstanding_total = zero
        outstanding_rows  = []

        for fund in funds:
            self.stdout.write(self.style.SQL_TABLE(f'\n--- {fund.name} ---'))
            any_period = False
            for month_date in months:
                expected = get_tariff(user.id, fund.id, month_date)
                if expected is None:
                    continue
                any_period = True
                period = month_date.strftime('%Y-%m')

                note = notes.get((user.id, fund.id, period))
                if note:
                    self.stdout.write(
                        f'  {period}  expected={fmt_rupiah(expected)}  '
                        f'-> SKIPPED (DueNote: {note["reason_label"]} — {note["note"] or "no note"})'
                    )
                    continue

                data          = paid.get((user.id, fund.id, period))
                entries       = data['entries'] if data else []
                total_paid    = data['total'] if data else zero
                completion_at = _period_completion_date(entries, expected)

                if completion_at is None:
                    counts['unpaid'] += 1
                    owed = max(expected - total_paid, zero)
                    outstanding_total += owed
                    outstanding_rows.append((fund.name, period, expected, total_paid, owed))
                    status = f'UNPAID (paid {fmt_rupiah(total_paid)} of {fmt_rupiah(expected)}, outstanding {fmt_rupiah(owed)})'
                elif completion_at < month_date:
                    counts['early'] += 1
                    status = f'EARLY (paid in full {completion_at.isoformat()})'
                elif completion_at <= date(month_date.year, month_date.month, PAYMENT_GRACE_DAY):
                    counts['ontime'] += 1
                    status = f'ON_TIME (paid in full {completion_at.isoformat()})'
                else:
                    counts['late'] += 1
                    status = f'LATE (paid in full {completion_at.isoformat()})'

                self.stdout.write(f'  {period}  expected={fmt_rupiah(expected)}  -> {status}')
                for e in entries:
                    when = timezone.localtime(e['occurred_at']).isoformat() if e['occurred_at'] else '(no date)'
                    self.stdout.write(f'      payment: {fmt_rupiah(e["amount"])} on {when}  (transaction #{e["transaction_id"]})')

            if not any_period:
                self.stdout.write('  (no tariff for this fund in the inspected range)')

        self.stdout.write(self.style.SQL_TABLE('\n--- Other income (non-routine) ---'))
        other_qs = (
            TransactionItem.objects
            .filter(
                transaction__deleted_at__isnull=True,
                transaction__direction=Transaction.Direction.IN,
                transaction__transfer__isnull=True,
                transaction__occurred_at__year=year,
                transaction__user_id=user.id,
                fund__deleted_at__isnull=True,
                routine__isnull=True,
            )
            .select_related('transaction', 'fund')
            .order_by('transaction__occurred_at')
        )
        other_total = zero
        for item in other_qs:
            txn  = item.transaction
            when = timezone.localtime(txn.occurred_at).isoformat() if txn.occurred_at else '(no date)'
            note = f'  note: "{txn.note}"' if txn.note else ''
            self.stdout.write(
                f'  {when}  transaction #{txn.id}  fund={item.fund.name}  {fmt_rupiah(item.nominal)}{note}'
            )
            other_total += item.nominal
        if not other_qs:
            self.stdout.write('  (none)')
        self.stdout.write(f'  Total other income: {fmt_rupiah(other_total)}')

        self.stdout.write(self.style.SQL_TABLE('\n--- Outstanding periods ---'))
        if outstanding_rows:
            for fund_name, period, expected, total_paid_, owed in outstanding_rows:
                self.stdout.write(
                    f'  {fund_name}  {period}  expected={fmt_rupiah(expected)}  '
                    f'paid={fmt_rupiah(total_paid_)}  owed={fmt_rupiah(owed)}'
                )
        else:
            self.stdout.write('  (none)')
        self.stdout.write(f'  Total outstanding: {fmt_rupiah(outstanding_total)}')

        score = (
            counts['early'] * POINTS_EARLY_PERIOD
            + counts['ontime'] * POINTS_ONTIME_PERIOD
            + counts['late'] * POINTS_LATE_PERIOD
            + other_total * POINTS_PER_RUPIAH
            - outstanding_total * POINTS_PER_RUPIAH
        )

        self.stdout.write(self.style.MIGRATE_HEADING('\n--- Summary (should match the Leaderboard page) ---'))
        self.stdout.write(f'  Early:          {counts["early"]}')
        self.stdout.write(f'  On-time:        {counts["ontime"]}')
        self.stdout.write(f'  Late:           {counts["late"]}')
        self.stdout.write(f'  Unpaid periods: {counts["unpaid"]}')
        self.stdout.write(f'  Other income:   {fmt_rupiah(other_total)}')
        self.stdout.write(f'  Outstanding:    {fmt_rupiah(outstanding_total)}')
        self.stdout.write(f'  Score:          {score:.1f}')
