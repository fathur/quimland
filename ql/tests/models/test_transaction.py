from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ql.models import Fund, Transaction, TransactionItem, Wallet, WalletTransfer

User = get_user_model()


class TransactionDeleteCascadeTests(TestCase):
    """Transaction.delete()/force_delete() must cascade to its TransactionItems.

    Found via production data reconciliation: transaction #433 was soft-deleted
    but its item #917 was left active, silently distorting fund totals.
    """

    def setUp(self):
        self.creator = User.objects.create_user(username='treasurer', is_staff=True)
        self.fund = Fund.objects.create(name='General', kind=Fund.Kind.ROUTINE)
        self.wallet = Wallet.objects.create(name='Cash Box', kind='CASH')

    def _make_transaction(self, direction=Transaction.Direction.IN, nominal=Decimal('50000')):
        return Transaction.objects.create(
            direction=direction, nominal=nominal, wallet=self.wallet,
            user=self.creator, creator=self.creator,
        )

    def test_soft_delete_cascades_to_active_item(self):
        txn = self._make_transaction()
        item = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('50000'))

        txn.delete()

        item.refresh_from_db()
        self.assertIsNotNone(txn.deleted_at)
        self.assertIsNotNone(item.deleted_at)

    def test_soft_delete_cascades_to_multiple_items(self):
        txn = self._make_transaction(nominal=Decimal('50000'))
        item1 = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('30000'))
        item2 = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('20000'))

        txn.delete()

        item1.refresh_from_db()
        item2.refresh_from_db()
        self.assertIsNotNone(item1.deleted_at)
        self.assertIsNotNone(item2.deleted_at)

    def test_soft_delete_with_no_items_does_not_error(self):
        txn = self._make_transaction()

        txn.delete()  # should not raise

        self.assertIsNotNone(txn.deleted_at)

    def test_soft_deleted_transaction_excluded_from_default_manager(self):
        txn = self._make_transaction()
        TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('50000'))

        txn.delete()

        self.assertFalse(Transaction.objects.filter(pk=txn.pk).exists())
        self.assertTrue(Transaction.objects.with_deleted().filter(pk=txn.pk).exists())
        self.assertFalse(TransactionItem.objects.filter(transaction_id=txn.pk).exists())

    def test_force_delete_purges_active_item(self):
        txn = self._make_transaction()
        item = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('50000'))

        txn.force_delete()

        self.assertFalse(Transaction.objects.with_deleted().filter(pk=txn.pk).exists())
        self.assertFalse(TransactionItem.objects.with_deleted().filter(pk=item.pk).exists())

    def test_force_delete_purges_already_soft_deleted_item_too(self):
        # This is the scenario that would otherwise leave an orphaned row: an
        # item deleted independently of its transaction, then the transaction
        # itself gets force-deleted (permanently purged).
        txn = self._make_transaction()
        item = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('50000'))
        item.delete()

        txn.force_delete()

        self.assertFalse(Transaction.objects.with_deleted().filter(pk=txn.pk).exists())
        self.assertFalse(TransactionItem.objects.with_deleted().filter(pk=item.pk).exists())

    def test_force_delete_only_purges_items_of_that_transaction(self):
        txn1 = self._make_transaction()
        txn2 = self._make_transaction()
        item1 = TransactionItem.objects.create(transaction=txn1, fund=self.fund, nominal=Decimal('50000'))
        item2 = TransactionItem.objects.create(transaction=txn2, fund=self.fund, nominal=Decimal('50000'))

        txn1.force_delete()

        self.assertFalse(TransactionItem.objects.with_deleted().filter(pk=item1.pk).exists())
        self.assertTrue(TransactionItem.objects.with_deleted().filter(pk=item2.pk).exists())
        self.assertTrue(Transaction.objects.with_deleted().filter(pk=txn2.pk).exists())


class TransactionRestoreTests(TestCase):
    """Transaction.restore() must cascade to its TransactionItems, mirroring
    delete()/force_delete() — and a transfer leg restores as part of its whole
    WalletTransfer, same as it deletes as part of it.

    The admin's "Restore selected" action (BaseTransactionAdmin.restore_selected)
    now loops obj.restore() rather than calling the bulk queryset.restore(),
    for the same reason delete_queryset() loops obj.delete(): a raw queryset
    UPDATE bypasses these instance-level overrides entirely.
    """

    def setUp(self):
        self.creator = User.objects.create_user(username='treasurer', is_staff=True)
        self.fund = Fund.objects.create(name='General', kind=Fund.Kind.ROUTINE)
        self.wallet = Wallet.objects.create(name='Cash Box', kind='CASH')

    def _make_transaction(self, direction=Transaction.Direction.IN, nominal=Decimal('50000')):
        return Transaction.objects.create(
            direction=direction, nominal=nominal, wallet=self.wallet,
            user=self.creator, creator=self.creator,
        )

    # -- basic instance restore --

    def test_restore_clears_deleted_at(self):
        txn = self._make_transaction()
        txn.delete()

        txn.restore()

        self.assertIsNone(txn.deleted_at)

    def test_restore_persists_to_db(self):
        txn = self._make_transaction()
        txn.delete()

        txn.restore()

        txn.refresh_from_db()
        self.assertIsNone(txn.deleted_at)

    def test_restore_makes_transaction_visible_in_default_manager(self):
        txn = self._make_transaction()
        txn.delete()
        self.assertFalse(Transaction.objects.filter(pk=txn.pk).exists())

        txn.restore()

        self.assertTrue(Transaction.objects.filter(pk=txn.pk).exists())

    def test_restore_removes_transaction_from_deleted_only_manager(self):
        txn = self._make_transaction()
        txn.delete()
        self.assertTrue(Transaction.objects.deleted_only().filter(pk=txn.pk).exists())

        txn.restore()

        self.assertFalse(Transaction.objects.deleted_only().filter(pk=txn.pk).exists())

    def test_restore_on_never_deleted_transaction_is_a_noop(self):
        txn = self._make_transaction()

        txn.restore()  # should not raise

        self.assertIsNone(txn.deleted_at)
        self.assertTrue(Transaction.objects.filter(pk=txn.pk).exists())

    def test_restore_called_twice_is_idempotent(self):
        txn = self._make_transaction()
        txn.delete()

        txn.restore()
        txn.restore()

        self.assertIsNone(txn.deleted_at)

    def test_restore_only_updates_deleted_at_field(self):
        # restore() calls save(update_fields=['deleted_at']) — confirm other
        # fields survive a concurrent change made directly in the DB and
        # aren't clobbered by a full-row save.
        txn = self._make_transaction(nominal=Decimal('75000'))
        txn.delete()
        Transaction.objects.with_deleted().filter(pk=txn.pk).update(note='updated out of band')

        txn.restore()

        txn.refresh_from_db()
        self.assertEqual(txn.nominal, Decimal('75000'))
        self.assertEqual(txn.note, 'updated out of band')

    # -- restore cascades to items --

    def test_restore_also_restores_its_item(self):
        txn = self._make_transaction()
        item = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('50000'))
        txn.delete()

        txn.restore()

        item.refresh_from_db()
        self.assertIsNone(txn.deleted_at)
        self.assertIsNone(item.deleted_at)

    def test_restore_restores_all_items(self):
        txn = self._make_transaction()
        item1 = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('30000'))
        item2 = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('20000'))
        txn.delete()

        txn.restore()

        item1.refresh_from_db()
        item2.refresh_from_db()
        self.assertIsNone(item1.deleted_at)
        self.assertIsNone(item2.deleted_at)

    def test_restore_only_restores_items_of_that_transaction(self):
        txn1 = self._make_transaction()
        txn2 = self._make_transaction()
        item1 = TransactionItem.objects.create(transaction=txn1, fund=self.fund, nominal=Decimal('50000'))
        item2 = TransactionItem.objects.create(transaction=txn2, fund=self.fund, nominal=Decimal('50000'))
        txn1.delete()
        txn2.delete()

        txn1.restore()

        item1.refresh_from_db()
        item2.refresh_from_db()
        self.assertIsNone(item1.deleted_at)
        self.assertIsNotNone(item2.deleted_at)  # txn2 was never restored

    def test_restore_with_no_items_does_not_error(self):
        txn = self._make_transaction()
        txn.delete()

        txn.restore()  # should not raise

        self.assertIsNone(txn.deleted_at)

    def test_restore_makes_item_visible_in_default_manager(self):
        txn = self._make_transaction()
        item = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('50000'))
        txn.delete()
        self.assertFalse(TransactionItem.objects.filter(pk=item.pk).exists())

        txn.restore()

        self.assertTrue(TransactionItem.objects.filter(pk=item.pk).exists())

    # -- restoring a transfer leg cascades to its sibling + the transfer --
    # (mirrors Transaction.delete(), which routes through the transfer too)

    def test_restoring_one_leg_also_restores_sibling_and_transfer(self):
        wallet_b = Wallet.objects.create(name='Wallet B', kind='BANK')
        transfer = WalletTransfer.objects.create(
            from_wallet=self.wallet, to_wallet=wallet_b, nominal=Decimal('100000'),
            occurred_at=timezone.now(), creator=self.creator,
        )
        transfer.delete()  # cascades: both legs + transfer soft-deleted
        out_leg = Transaction.objects.with_deleted().get(pk=transfer.out_transaction_id)

        out_leg.restore()

        transfer.refresh_from_db()
        in_leg = Transaction.objects.with_deleted().get(pk=transfer.in_transaction_id)
        self.assertIsNone(out_leg.deleted_at)
        self.assertIsNone(transfer.deleted_at)
        self.assertIsNone(in_leg.deleted_at)

    # -- bulk restore via SoftDeleteQuerySet.restore() does NOT cascade —
    #    this is the raw queryset path the admin action deliberately avoids
    #    by looping obj.restore() instead (see restore_selected) --

    def test_queryset_bulk_restore(self):
        txn1 = self._make_transaction()
        txn2 = self._make_transaction()
        txn1.delete()
        txn2.delete()

        restored_count = Transaction.objects.with_deleted().filter(pk__in=[txn1.pk, txn2.pk]).restore()

        self.assertEqual(restored_count, 2)
        self.assertTrue(Transaction.objects.filter(pk=txn1.pk).exists())
        self.assertTrue(Transaction.objects.filter(pk=txn2.pk).exists())

    def test_queryset_bulk_restore_only_affects_filtered_rows(self):
        txn1 = self._make_transaction()
        txn2 = self._make_transaction()
        txn1.delete()
        txn2.delete()

        Transaction.objects.with_deleted().filter(pk=txn1.pk).restore()

        self.assertTrue(Transaction.objects.filter(pk=txn1.pk).exists())
        self.assertFalse(Transaction.objects.filter(pk=txn2.pk).exists())

    def test_queryset_bulk_restore_does_not_cascade_to_items(self):
        txn = self._make_transaction()
        item = TransactionItem.objects.create(transaction=txn, fund=self.fund, nominal=Decimal('50000'))
        txn.delete()

        Transaction.objects.with_deleted().filter(pk=txn.pk).restore()

        item.refresh_from_db()
        self.assertIsNotNone(item.deleted_at)
