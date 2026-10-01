from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ql.fee.admin.dashboards.garbage import RoutinePayoutForm
from ql.fee.models import Fund, ItemRoutine, RoutinePayout, Transaction, TransactionItem
from ql.fee.services.pass_through import pass_through_ledger, payable_items

User = get_user_model()
D = Decimal
TODAY = date(2026, 10, 2)


class LedgerTestBase(TestCase):
    def setUp(self):
        self.treasurer = User.objects.create_user(username='treasurer', is_staff=True)
        self.resident = User.objects.create_user(username='warga')
        self.fund = Fund.objects.create(name='Sampah', kind=Fund.Kind.ROUTINE, is_pass_through=True)

    def collect(self, period, nominal, count=1):
        for _ in range(count):
            tx = Transaction.objects.create(
                direction='IN', nominal=D(nominal), user=self.resident, creator=self.treasurer,
                occurred_at=timezone.make_aware(datetime(2026, 9, 20, 10)),
            )
            item = TransactionItem.objects.create(transaction=tx, fund=self.fund, nominal=D(nominal))
            ItemRoutine.objects.create(transaction_item=item, period=period)

    def expense(self, nominal, name='Gaji petugas'):
        tx = Transaction.objects.create(
            direction='OUT', nominal=D(nominal), user=self.treasurer, creator=self.treasurer,
            occurred_at=timezone.make_aware(datetime(2026, 9, 25, 10)),
        )
        return TransactionItem.objects.create(transaction=tx, fund=self.fund, nominal=D(nominal), name=name)

    def allocate(self, item, period, amount):
        return RoutinePayout.objects.create(transaction_item=item, period=period, amount=D(amount))

    def row(self, ledger, period):
        return next(r for r in ledger['rows'] if r['period'] == period)


class LedgerTests(LedgerTestBase):
    def test_collected_minus_paid_is_remaining(self):
        self.collect('2026-08', 20000, count=5)
        item = self.expense(100000)
        self.allocate(item, '2026-08', 100000)

        ledger = pass_through_ledger(self.fund, TODAY)
        aug = self.row(ledger, '2026-08')
        self.assertEqual((aug['collected'], aug['paid'], aug['remaining']), (D(100000), D(100000), D(0)))
        self.assertEqual(ledger['due_now'], D(0))

    def test_late_payments_create_rapel_on_an_already_paid_month(self):
        # Aug: 5 payers → paid out 100k. Later 15 more pay for August late.
        self.collect('2026-08', 20000, count=5)
        self.allocate(self.expense(100000), '2026-08', 100000)
        self.collect('2026-08', 20000, count=15)

        ledger = pass_through_ledger(self.fund, TODAY)
        aug = self.row(ledger, '2026-08')
        self.assertEqual(aug['collected'], D(400000))
        self.assertEqual(aug['remaining'], D(300000))
        self.assertEqual(ledger['due_now'], D(300000))

    def test_advance_payment_is_held_not_due(self):
        self.collect('2026-10', 20000, count=3)   # current month
        self.collect('2026-11', 20000, count=4)   # next month, paid in advance

        ledger = pass_through_ledger(self.fund, TODAY)
        self.assertTrue(self.row(ledger, '2026-11')['is_held'])
        self.assertEqual(ledger['due_now'], D(60000))
        self.assertEqual(ledger['held'], D(80000))
        self.assertEqual(ledger['collected_total'], D(60000))

    def test_rows_have_no_gaps_and_reach_current_month(self):
        self.collect('2026-07', 20000)
        periods = [r['period'] for r in pass_through_ledger(self.fund, TODAY)['rows']]
        self.assertEqual(periods, ['2026-07', '2026-08', '2026-09', '2026-10'])

    def test_deleted_transactions_are_ignored(self):
        self.collect('2026-09', 20000, count=2)
        item = self.expense(30000)
        self.allocate(item, '2026-09', 30000)
        item.transaction.delete()                       # soft-deletes the expense + items
        Transaction.objects.filter(direction='IN').first().delete()

        ledger = pass_through_ledger(self.fund, TODAY)
        sep = self.row(ledger, '2026-09')
        self.assertEqual((sep['collected'], sep['paid']), (D(20000), D(0)))

    def test_item_split_across_two_months(self):
        self.collect('2026-08', 20000, count=2)
        self.collect('2026-09', 20000, count=3)
        item = self.expense(100000)
        self.allocate(item, '2026-08', 40000)
        self.allocate(item, '2026-09', 60000)

        self.assertFalse(payable_items(self.fund).filter(pk=item.pk).exists())
        ledger = pass_through_ledger(self.fund, TODAY)
        self.assertEqual(ledger['due_now'], D(0))


class RoutinePayoutFormTests(LedgerTestBase):
    def form(self, item, period, amount):
        return RoutinePayoutForm(
            {'period': period, 'amount': str(amount), 'transaction_item': item.pk},
            fund=self.fund, today=TODAY,
        )

    def test_valid_allocation(self):
        self.collect('2026-09', 20000, count=5)
        item = self.expense(100000)
        self.assertTrue(self.form(item, '2026-09', 100000).is_valid())

    def test_rejects_more_than_collected_for_period(self):
        self.collect('2026-09', 20000, count=2)
        item = self.expense(100000)
        form = self.form(item, '2026-09', 50000)
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)

    def test_rejects_more_than_item_unallocated(self):
        self.collect('2026-09', 20000, count=10)
        item = self.expense(100000)
        self.allocate(item, '2026-09', 80000)
        form = self.form(item, '2026-09', 30000)
        self.assertFalse(form.is_valid())

    def test_rejects_future_period(self):
        self.collect('2026-11', 20000, count=5)
        item = self.expense(100000)
        form = self.form(item, '2026-11', 50000)
        self.assertFalse(form.is_valid())
        self.assertIn('period', form.errors)

    def test_rejects_item_of_other_fund(self):
        other = Fund.objects.create(name='Kas', kind=Fund.Kind.ROUTINE)
        tx = Transaction.objects.create(direction='OUT', nominal=D(1000), user=self.treasurer, creator=self.treasurer)
        item = TransactionItem.objects.create(transaction=tx, fund=other, nominal=D(1000))
        self.collect('2026-09', 20000)
        self.assertFalse(self.form(item, '2026-09', 1000).is_valid())


class GarbageDashboardViewTests(LedgerTestBase):
    def test_page_renders_and_allocation_posts(self):
        admin_user = User.objects.create_superuser(username='root', password='pw')
        self.client.force_login(admin_user)
        today = timezone.localdate()
        period = today.strftime('%Y-%m')
        self.collect(period, 20000, count=5)
        item = self.expense(100000)

        url = reverse('admin:garbage_dashboard')
        self.assertEqual(self.client.get(url).status_code, 200)

        resp = self.client.post(url, {'period': period, 'amount': '100000', 'transaction_item': item.pk})
        self.assertRedirects(resp, url)
        self.assertEqual(RoutinePayout.objects.get().amount, D(100000))

        # removing the allocation brings the balance back
        payout = RoutinePayout.objects.get()
        self.client.post(url, {'delete_id': payout.pk})
        self.assertFalse(RoutinePayout.objects.exists())

    def test_invalid_post_rerenders_form_with_error(self):
        self.client.force_login(User.objects.create_superuser(username='root', password='pw'))
        period = timezone.localdate().strftime('%Y-%m')
        self.collect(period, 20000)
        item = self.expense(100000)

        resp = self.client.post(reverse('admin:garbage_dashboard'), {'period': period, 'amount': '50000', 'transaction_item': item.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'is left to pay out for')
        self.assertContains(resp, 'gb-form-config')
        self.assertFalse(RoutinePayout.objects.exists())

    def test_page_without_pass_through_fund(self):
        Fund.objects.update(is_pass_through=False)
        self.client.force_login(User.objects.create_superuser(username='root', password='pw'))
        self.assertEqual(self.client.get(reverse('admin:garbage_dashboard')).status_code, 200)
