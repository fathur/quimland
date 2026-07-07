"""
Management command: seed_finance
Usage: poetry run python manage.py seed_finance [--reset]

Inserts a minimal but illustrative dataset that demonstrates:
  - One LATE garbage payment: user pays June 5 for April, May, June
    → all three payout on June 10
  - One ADVANCE garbage payment: user pays June 5 for July, Aug, Sep
    → each held until its own month (Jul 10 / Aug 10 / Sep 10)

Run --reset to wipe existing seed data before reinserting.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from ql.models import (
    CashEntry, Fund, FundDue, Payment, PaymentBatch,
    Payout, SalaryRate, Setting, Tariff,
)

User = get_user_model()
TODAY = datetime.date(2026, 6, 26)   # frozen demo date


class Command(BaseCommand):
    help = 'Seed the RT finance database with demo data.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Delete existing seed data before inserting.')

    def handle(self, *args, **options):
        if options['reset']:
            self._reset()
        with transaction.atomic():
            self._run()
        self.stdout.write(self.style.SUCCESS('Seed complete.'))

    # ------------------------------------------------------------------

    def _reset(self):
        self.stdout.write('Resetting seed data …')
        CashEntry.objects.all().delete()
        Payout.objects.all().delete()
        Payment.objects.all().delete()
        PaymentBatch.objects.all().delete()
        FundDue.objects.all().delete()
        Tariff.objects.all().delete()
        SalaryRate.objects.all().delete()
        Fund.objects.all().delete()
        Setting.objects.all().delete()
        User.objects.filter(username__in=[
            'admin_rt', 'budi', 'sari', 'tono',
        ]).delete()

    def _run(self):
        # ── Users ─────────────────────────────────────────────────────
        admin, _ = User.objects.get_or_create(
            username='admin_rt',
            defaults=dict(first_name='Admin', last_name='RT', is_staff=True, is_superuser=True),
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.save(update_fields=['is_staff', 'is_superuser'])
        budi, _ = User.objects.get_or_create(
            username='budi',
            defaults=dict(first_name='Budi', last_name='Santoso'),
        )
        sari, _ = User.objects.get_or_create(
            username='sari',
            defaults=dict(first_name='Sari', last_name='Dewi'),
        )
        tono, _ = User.objects.get_or_create(
            username='tono',
            defaults=dict(first_name='Tono', last_name='Wibowo'),
        )
        self.stdout.write('  Users: admin_rt, budi, sari, tono')

        # ── Settings ──────────────────────────────────────────────────
        Setting.objects.get_or_create(key='security_day',  defaults={'value': '10'})
        Setting.objects.get_or_create(key='garbage_days',  defaults={'value': '10,25'})

        # ── Salary rate ───────────────────────────────────────────────
        rate, _ = SalaryRate.objects.get_or_create(
            payee='SECURITY',
            start_from=datetime.date(2026, 1, 1),
            defaults=dict(amount=Decimal('900000'), end_to=None),
        )
        self.stdout.write('  SalaryRate: 900,000/mo from 2026-01-01')

        # ── Funds ─────────────────────────────────────────────────────
        general, _ = Fund.objects.get_or_create(
            kind=Fund.Kind.GENERAL,
            defaults=dict(name='Kas RT', description='General RT fund'),
        )
        garbage_fund, _ = Fund.objects.get_or_create(
            kind=Fund.Kind.GARBAGE,
            defaults=dict(name='Dana Sampah', description='Garbage pass-through'),
        )
        pump_fund, _ = Fund.objects.get_or_create(
            kind=Fund.Kind.EARMARKED,
            name='Water Pump Repair',
            defaults=dict(description='Replace water pump', target_amount=Decimal('3000000')),
        )
        self.stdout.write('  Funds: Kas RT, Dana Sampah, Water Pump Repair')

        # ── FundDues (earmarked) ───────────────────────────────────────
        for user, amount in [(budi, '500000'), (sari, '500000'), (tono, '500000')]:
            FundDue.objects.get_or_create(
                fund=pump_fund, user=user,
                defaults=dict(expected_amount=Decimal(amount)),
            )

        # ── Tariffs ───────────────────────────────────────────────────
        start = datetime.date(2026, 1, 1)
        for user, monthly, garbage in [
            (budi, '70000', '30000'),   # occupied
            (sari, '70000', '30000'),   # occupied
            (tono, '35000', '0'),       # vacant – no garbage iuran
        ]:
            Tariff.objects.get_or_create(
                user=user, kind=Tariff.Kind.MONTHLY, start_from=start,
                defaults=dict(nominal=Decimal(monthly)),
            )
            if Decimal(garbage) > 0:
                Tariff.objects.get_or_create(
                    user=user, kind=Tariff.Kind.GARBAGE, start_from=start,
                    defaults=dict(nominal=Decimal(garbage)),
                )
        self.stdout.write('  Tariffs: budi 70K+30K, sari 70K+30K, tono 35K (vacant, no garbage)')

        # ── Payments ─────────────────────────────────────────────────
        # budi: pays monthly Jan-May on time
        for period in ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05']:
            batch = PaymentBatch.objects.create(
                user=budi,
                paid_at=datetime.datetime(
                    int(period[:4]), int(period[5:7]), 8,
                    tzinfo=datetime.timezone.utc,
                ),
                creator=admin,
            )
            Payment.objects.create(batch=batch, kind='MONTHLY', period=period, nominal=Decimal('70000'))

        # sari: pays monthly Jan-Mar on time; misses Apr and May (will show in report)
        for period in ['2026-01', '2026-02', '2026-03']:
            batch = PaymentBatch.objects.create(
                user=sari,
                paid_at=datetime.datetime(
                    int(period[:4]), int(period[5:7]), 7,
                    tzinfo=datetime.timezone.utc,
                ),
                creator=admin,
            )
            Payment.objects.create(batch=batch, kind='MONTHLY', period=period, nominal=Decimal('70000'))

        # LATE GARBAGE: budi pays on 5 June 2026 for Apr, May, Jun garbage
        # → all three payout_date = 10 June 2026
        late_batch = PaymentBatch.objects.create(
            user=budi,
            paid_at=datetime.datetime(2026, 6, 5, 10, 0, tzinfo=datetime.timezone.utc),
            creator=admin,
            note='Late payment: Apr/May/Jun garbage paid together on 5 June',
        )
        for period in ['2026-04', '2026-05', '2026-06']:
            Payment.objects.create(
                batch=late_batch, kind='GARBAGE', period=period, nominal=Decimal('30000'),
            )
        self.stdout.write(
            '  LATE case: budi paid Apr+May+Jun garbage on 5 Jun → all payout on 10 Jun'
        )

        # ADVANCE GARBAGE: sari pays on 5 June 2026 for Jul, Aug, Sep
        # → payout Jul 10 / Aug 10 / Sep 10 respectively
        advance_batch = PaymentBatch.objects.create(
            user=sari,
            paid_at=datetime.datetime(2026, 6, 5, 11, 0, tzinfo=datetime.timezone.utc),
            creator=admin,
            note='Advance payment: Jul/Aug/Sep garbage paid on 5 June',
        )
        for period in ['2026-07', '2026-08', '2026-09']:
            Payment.objects.create(
                batch=advance_batch, kind='GARBAGE', period=period, nominal=Decimal('30000'),
            )
        self.stdout.write(
            '  ADVANCE case: sari paid Jul+Aug+Sep garbage on 5 Jun → payout Jul 10, Aug 10, Sep 10'
        )

        # ── Payouts ───────────────────────────────────────────────────
        # Security: Jan-May paid in full, June not yet
        for month in range(1, 6):
            Payout.objects.get_or_create(
                payee='SECURITY',
                period=f'2026-0{month}',
                payout_date=datetime.date(2026, month, 10),
                defaults=dict(amount=Decimal('900000'), creator=admin),
            )

        # Sanitation: Jan-Mar payout done for budi (garbage), Jun not yet
        for month in [1, 2, 3]:
            Payout.objects.get_or_create(
                payee='SANITATION',
                period=f'2026-0{month}',
                payout_date=datetime.date(2026, month, 10),
                defaults=dict(amount=Decimal('30000'), creator=admin, note='budi only'),
            )
        self.stdout.write('  Payouts: security Jan-May done; sanitation Jan-Mar done')

        # ── Cash entries (General fund) ────────────────────────────────
        CashEntry.objects.get_or_create(
            fund=general,
            direction='IN',
            occurred_at=datetime.datetime(2026, 3, 15, tzinfo=datetime.timezone.utc),
            user=budi,
            defaults=dict(
                amount=Decimal('200000'),
                category='donation',
                description='Sumbangan acara 17-an',
                creator=admin,
            ),
        )
        CashEntry.objects.get_or_create(
            fund=general,
            direction='OUT',
            occurred_at=datetime.datetime(2026, 4, 2, tzinfo=datetime.timezone.utc),
            user=admin,
            defaults=dict(
                amount=Decimal('150000'),
                category='supplies',
                description='Beli perlengkapan kebersihan',
                creator=admin,
            ),
        )

        # Pump fund: budi & sari have contributed, tono has not
        CashEntry.objects.get_or_create(
            fund=pump_fund,
            direction='IN',
            occurred_at=datetime.datetime(2026, 5, 10, tzinfo=datetime.timezone.utc),
            user=budi,
            defaults=dict(amount=Decimal('500000'), category='earmarked', creator=admin),
        )
        CashEntry.objects.get_or_create(
            fund=pump_fund,
            direction='IN',
            occurred_at=datetime.datetime(2026, 5, 12, tzinfo=datetime.timezone.utc),
            user=sari,
            defaults=dict(amount=Decimal('500000'), category='earmarked', creator=admin),
        )
        self.stdout.write('  CashEntries: General (donation + expense); Pump (budi & sari paid, tono unpaid)')
