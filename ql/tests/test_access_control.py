import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from ql.models import Fund, ItemRoutine, Tariff, Transaction, TransactionItem, UserProperty
from ql.tasks.access_control import sync_resident_admin_access

User = get_user_model()

# Aug 1 2026 -> _months_through() covers Jan-Jul 2026 (grace day is the 5th,
# and day 1 of the current month hasn't passed it yet).
TODAY = datetime.date(2026, 8, 1)


class SyncResidentAdminAccessTests(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(username='treasurer', is_staff=True)
        self.fund = Fund.objects.create(name='Monthly Dues', kind=Fund.Kind.ROUTINE)

    def _make_resident(self, username, is_staff=False, is_active=True, is_superuser=False,
                        home_number='A1', password=None):
        # create_user(password=None) leaves an unusable password, matching
        # the real `add_user` command's default (see cmd-add-user.txt).
        user = User.objects.create_user(
            username=username, password=password,
            is_staff=is_staff, is_active=is_active, is_superuser=is_superuser,
        )
        UserProperty.objects.create(
            user=user, occupancy_status=UserProperty.OccupancyStatus.OCCUPIED, home_number=home_number,
        )
        return user

    def _give_tariff(self, user, start_from, nominal=Decimal('50000')):
        return Tariff.objects.create(user=user, fund=self.fund, nominal=nominal, start_from=start_from)

    def _pay(self, user, period, nominal):
        txn = Transaction.objects.create(
            direction=Transaction.Direction.IN, nominal=nominal,
            occurred_at=datetime.datetime(int(period[:4]), int(period[5:7]), 1, tzinfo=datetime.timezone.utc),
            user=user, creator=self.creator,
        )
        item = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=nominal)
        ItemRoutine.objects.create(transaction_item=item, period=period)

    def test_outstanding_resident_gets_staff_revoked(self):
        resident = self._make_resident('budi', is_staff=True)
        self._give_tariff(resident, datetime.date(2026, 1, 1))  # unpaid Jan-Jul

        result = sync_resident_admin_access(today=TODAY)

        resident.refresh_from_db()
        self.assertFalse(resident.is_staff)
        self.assertTrue(resident.is_active)  # untouched by design
        self.assertEqual(result, {'disabled': 1, 'enabled': 0, 'new_credentials': []})

    def test_resident_with_no_tariff_gets_staff_granted(self):
        resident = self._make_resident('sari', is_staff=False, password='s3curePass!')

        result = sync_resident_admin_access(today=TODAY)

        resident.refresh_from_db()
        self.assertTrue(resident.is_staff)
        self.assertEqual(result, {'disabled': 0, 'enabled': 1, 'new_credentials': []})

    def test_resident_fully_paid_gets_staff_granted(self):
        resident = self._make_resident('tono', is_staff=False, password='s3curePass!')
        self._give_tariff(resident, datetime.date(2026, 1, 1))
        for month in range(1, 8):
            self._pay(resident, f'2026-{month:02d}', Decimal('50000'))

        result = sync_resident_admin_access(today=TODAY)

        resident.refresh_from_db()
        self.assertTrue(resident.is_staff)
        self.assertEqual(result, {'disabled': 0, 'enabled': 1, 'new_credentials': []})

    def test_partially_paid_resident_stays_outstanding(self):
        resident = self._make_resident('wati', is_staff=True)
        self._give_tariff(resident, datetime.date(2026, 1, 1))
        self._pay(resident, '2026-01', Decimal('20000'))  # tariff is 50000 -> still short

        result = sync_resident_admin_access(today=TODAY)

        resident.refresh_from_db()
        self.assertFalse(resident.is_staff)
        self.assertEqual(result, {'disabled': 1, 'enabled': 0, 'new_credentials': []})

    def test_superuser_never_touched(self):
        superuser = self._make_resident('admin_rt', is_staff=True, is_superuser=True)
        self._give_tariff(superuser, datetime.date(2026, 1, 1))  # would be outstanding if in scope

        sync_resident_admin_access(today=TODAY)

        superuser.refresh_from_db()
        self.assertTrue(superuser.is_staff)

    def test_user_without_property_not_touched(self):
        non_resident = User.objects.create_user(username='ghost', is_staff=True)

        sync_resident_admin_access(today=TODAY)

        non_resident.refresh_from_db()
        self.assertTrue(non_resident.is_staff)

    def test_does_not_touch_groups(self):
        self._make_resident('lina', is_staff=False)

        sync_resident_admin_access(today=TODAY)

        self.assertEqual(Group.objects.count(), 0)

    def test_mixed_batch_counts(self):
        outstanding_resident = self._make_resident('agus', is_staff=True)
        self._give_tariff(outstanding_resident, datetime.date(2026, 1, 1))

        clear_resident = self._make_resident('heri', is_staff=False, password='s3curePass!')

        result = sync_resident_admin_access(today=TODAY)

        outstanding_resident.refresh_from_db()
        clear_resident.refresh_from_db()
        self.assertFalse(outstanding_resident.is_staff)
        self.assertTrue(clear_resident.is_staff)
        self.assertEqual(result, {'disabled': 1, 'enabled': 1, 'new_credentials': []})

    def test_already_correct_state_is_a_noop(self):
        # Already staff, no dues, AND already has a real password -> nothing to do.
        resident = self._make_resident('candra', is_staff=True, password='s3curePass!')

        result = sync_resident_admin_access(today=TODAY)

        resident.refresh_from_db()
        self.assertTrue(resident.is_staff)
        self.assertTrue(resident.check_password('s3curePass!'))
        self.assertEqual(result, {'disabled': 0, 'enabled': 0, 'new_credentials': []})

    # ── Password bootstrapping ───────────────────────────────────────────────

    def test_password_generated_when_granting_access(self):
        resident = self._make_resident('dewi', is_staff=False)  # no password (default)
        self.assertFalse(resident.has_usable_password())

        result = sync_resident_admin_access(today=TODAY)

        resident.refresh_from_db()
        self.assertTrue(resident.is_staff)
        self.assertTrue(resident.has_usable_password())
        self.assertEqual(len(result['new_credentials']), 1)
        cred = result['new_credentials'][0]
        self.assertEqual(cred['username'], 'dewi')
        self.assertTrue(resident.check_password(cred['password']))

    def test_no_new_password_when_resident_already_has_one(self):
        resident = self._make_resident('yanto', is_staff=False, password='alreadySet1')

        result = sync_resident_admin_access(today=TODAY)

        resident.refresh_from_db()
        self.assertTrue(resident.is_staff)
        self.assertEqual(result['new_credentials'], [])
        self.assertTrue(resident.check_password('alreadySet1'))  # unchanged

    def test_already_staff_resident_without_password_still_gets_one(self):
        # Already granted access previously, but never actually got a password.
        resident = self._make_resident('galang', is_staff=True)

        result = sync_resident_admin_access(today=TODAY)

        resident.refresh_from_db()
        self.assertTrue(resident.is_staff)
        self.assertTrue(resident.has_usable_password())
        self.assertEqual(result['enabled'], 0)  # was already staff -> not counted as newly enabled
        self.assertEqual(len(result['new_credentials']), 1)
        self.assertEqual(result['new_credentials'][0]['username'], 'galang')

    def test_outstanding_resident_is_not_given_a_password(self):
        resident = self._make_resident('bagas', is_staff=True)  # passwordless
        self._give_tariff(resident, datetime.date(2026, 1, 1))  # unpaid -> outstanding

        result = sync_resident_admin_access(today=TODAY)

        resident.refresh_from_db()
        self.assertFalse(resident.is_staff)
        self.assertFalse(resident.has_usable_password())  # still untouched
        self.assertEqual(result['new_credentials'], [])
