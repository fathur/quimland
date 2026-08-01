import datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ql.models import Payment, PaymentBatch, Tariff
from ql.management.commands import record as record_module

User = get_user_model()


class RecordCommandTests(TestCase):

    def setUp(self):
        self.resident = User.objects.create_user(username='resident')
        self.admin = User.objects.create_user(username='admin', is_staff=True)
        # Open-ended tariffs covering 2026 onwards for both kinds
        Tariff.objects.create(
            user=self.resident, kind=Tariff.Kind.MONTHLY,
            nominal=Decimal('70000'), start_from=datetime.date(2026, 1, 1),
        )
        Tariff.objects.create(
            user=self.resident, kind=Tariff.Kind.GARBAGE,
            nominal=Decimal('30000'), start_from=datetime.date(2026, 1, 1),
        )

    def call(self, *args, **kwargs):
        out = StringIO()
        call_command('record', *args, stdout=out, stderr=StringIO(), **kwargs)
        return out.getvalue()

    def _periods(self, kind):
        return list(
            Payment.objects.filter(batch__user=self.resident, kind=kind)
            .order_by('period').values_list('period', flat=True)
        )

    def _seed(self, kind, period, nominal=None):
        if nominal is None:
            nominal = Decimal('70000') if kind == Payment.Kind.MONTHLY else Decimal('30000')
        batch = PaymentBatch.objects.create(
            user=self.resident,
            paid_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
            creator=self.admin,
        )
        Payment.objects.create(batch=batch, kind=kind, period=period, nominal=nominal)

    # ── Validation errors ────────────────────────────────────────────────────

    def test_no_kind_flag_raises(self):
        with self.assertRaises(CommandError):
            self.call(self.resident.pk)

    def test_zero_count_raises(self):
        with self.assertRaises(CommandError):
            self.call(self.resident.pk, general=0)

    def test_negative_count_raises(self):
        with self.assertRaises(CommandError):
            self.call(self.resident.pk, garbage=-1)

    def test_unknown_user_raises(self):
        with self.assertRaises(CommandError):
            self.call(99999, general=1)

    def test_unknown_creator_raises(self):
        with self.assertRaises(CommandError):
            self.call(self.resident.pk, general=1, year=2026, creator=99999)

    def test_missing_tariff_raises(self):
        other = User.objects.create_user(username='notariff')
        with self.assertRaises(CommandError):
            self.call(other.pk, general=1, year=2026)

    # ── First-time payment (no prior history) ───────────────────────────────

    def test_first_monthly_starts_from_january(self):
        self.call(self.resident.pk, general=3, year=2026)
        self.assertEqual(self._periods(Payment.Kind.MONTHLY),
                         ['2026-01', '2026-02', '2026-03'])

    def test_first_garbage_starts_from_january(self):
        self.call(self.resident.pk, garbage=2, year=2026)
        self.assertEqual(self._periods(Payment.Kind.GARBAGE),
                         ['2026-01', '2026-02'])

    def test_both_kinds_first_time(self):
        self.call(self.resident.pk, general=2, garbage=2, year=2026)
        self.assertEqual(self._periods(Payment.Kind.MONTHLY), ['2026-01', '2026-02'])
        self.assertEqual(self._periods(Payment.Kind.GARBAGE), ['2026-01', '2026-02'])

    def test_both_kinds_go_into_single_batch(self):
        self.call(self.resident.pk, general=2, garbage=2, year=2026)
        self.assertEqual(PaymentBatch.objects.filter(user=self.resident).count(), 1)

    # ── Continuing from last payment ─────────────────────────────────────────

    def test_continues_after_last_monthly(self):
        self._seed(Payment.Kind.MONTHLY, '2026-03')
        self.call(self.resident.pk, general=2, year=2026)
        new = [p for p in self._periods(Payment.Kind.MONTHLY) if p > '2026-03']
        self.assertEqual(new, ['2026-04', '2026-05'])

    def test_continues_after_last_garbage(self):
        self._seed(Payment.Kind.GARBAGE, '2026-05')
        self.call(self.resident.pk, garbage=2, year=2026)
        new = [p for p in self._periods(Payment.Kind.GARBAGE) if p > '2026-05']
        self.assertEqual(new, ['2026-06', '2026-07'])

    def test_continues_across_year_boundary(self):
        self._seed(Payment.Kind.MONTHLY, '2026-11')
        self.call(self.resident.pk, general=3, year=2026)
        new = [p for p in self._periods(Payment.Kind.MONTHLY) if p > '2026-11']
        self.assertEqual(new, ['2026-12', '2027-01', '2027-02'])

    def test_each_kind_continues_independently(self):
        # Monthly paid up to March; garbage never paid
        self._seed(Payment.Kind.MONTHLY, '2026-03')
        self.call(self.resident.pk, general=1, garbage=1, year=2026)
        # Monthly picks up from April, garbage starts from January
        self.assertEqual([p for p in self._periods(Payment.Kind.MONTHLY) if p > '2026-03'],
                         ['2026-04'])
        self.assertIn('2026-01', self._periods(Payment.Kind.GARBAGE))

    # ── DB state after a successful run ──────────────────────────────────────

    def test_nominal_matches_tariff(self):
        self.call(self.resident.pk, general=1, year=2026)
        p = Payment.objects.get(batch__user=self.resident, kind=Payment.Kind.MONTHLY)
        self.assertEqual(p.nominal, Decimal('70000'))

    def test_garbage_nominal_matches_tariff(self):
        self.call(self.resident.pk, garbage=1, year=2026)
        p = Payment.objects.get(batch__user=self.resident, kind=Payment.Kind.GARBAGE)
        self.assertEqual(p.nominal, Decimal('30000'))

    def test_default_creator_is_system_user(self):
        self.call(self.resident.pk, general=1, year=2026)
        batch = PaymentBatch.objects.get(user=self.resident)
        self.assertEqual(batch.creator.username, 'system')

    def test_explicit_creator_is_used(self):
        self.call(self.resident.pk, general=1, year=2026, creator=self.admin.pk)
        batch = PaymentBatch.objects.get(user=self.resident)
        self.assertEqual(batch.creator, self.admin)

    def test_correct_payment_count(self):
        self.call(self.resident.pk, general=4, garbage=3, year=2026)
        self.assertEqual(
            Payment.objects.filter(batch__user=self.resident).count(), 7
        )

    def test_output_contains_period_and_nominal(self):
        output = self.call(self.resident.pk, general=1, year=2026)
        self.assertIn('2026-01', output)
        self.assertIn('70', output)

    # ── Skip already-paid periods ─────────────────────────────────────────────

    def test_skip_already_paid_period(self):
        # Patch last_paid_period to return None so the command tries Jan 2026
        # even though a positive-nominal Jan payment already exists.
        self._seed(Payment.Kind.MONTHLY, '2026-01')
        with patch.object(record_module, 'last_paid_period', return_value=None):
            output = self.call(self.resident.pk, general=1, year=2026)
        self.assertIn('Nothing new to record', output)
        # No duplicate payment created
        self.assertEqual(
            Payment.objects.filter(
                batch__user=self.resident, kind=Payment.Kind.MONTHLY, period='2026-01'
            ).count(), 1
        )

    def test_partial_skip_records_remaining(self):
        # Jan already paid; patch last_paid_period to force trying Jan again,
        # so Jan is skipped and Feb is recorded.
        self._seed(Payment.Kind.MONTHLY, '2026-01')
        with patch.object(record_module, 'last_paid_period', return_value=None):
            self.call(self.resident.pk, general=2, year=2026)
        periods = self._periods(Payment.Kind.MONTHLY)
        self.assertIn('2026-01', periods)
        self.assertIn('2026-02', periods)
        # Only two payments total (the original Jan and the new Feb)
        self.assertEqual(
            Payment.objects.filter(
                batch__user=self.resident, kind=Payment.Kind.MONTHLY
            ).count(), 2
        )

    # ── Tariff date boundaries ────────────────────────────────────────────────

    def test_tariff_with_end_to_applies_within_range(self):
        # Tariff active only Jan–Jun 2026
        Tariff.objects.filter(user=self.resident, kind=Tariff.Kind.MONTHLY).delete()
        Tariff.objects.create(
            user=self.resident, kind=Tariff.Kind.MONTHLY,
            nominal=Decimal('65000'),
            start_from=datetime.date(2026, 1, 1),
            end_to=datetime.date(2026, 6, 30),
        )
        self.call(self.resident.pk, general=3, year=2026)
        self.assertEqual(
            Payment.objects.filter(
                batch__user=self.resident, kind=Payment.Kind.MONTHLY
            ).values_list('nominal', flat=True).first(),
            Decimal('65000'),
        )

    def test_tariff_expired_raises(self):
        # Tariff ended before the requested period
        Tariff.objects.filter(user=self.resident, kind=Tariff.Kind.MONTHLY).delete()
        Tariff.objects.create(
            user=self.resident, kind=Tariff.Kind.MONTHLY,
            nominal=Decimal('65000'),
            start_from=datetime.date(2025, 1, 1),
            end_to=datetime.date(2025, 12, 31),
        )
        with self.assertRaises(CommandError):
            self.call(self.resident.pk, general=1, year=2026)
