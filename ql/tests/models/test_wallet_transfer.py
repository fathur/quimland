from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ql.models import Fund, Transaction, TransactionItem, Wallet, WalletTransfer

User = get_user_model()


class WalletTransferDeleteCascadeTests(TestCase):
    """WalletTransfer <-> leg Transaction deleted_at must stay in sync.

    Found via production data reconciliation: transfer #12's OUT leg (#380)
    was soft-deleted directly (bypassing WalletTransfer.delete()), leaving its
    IN leg (#381) active — a Rp2,000,000 phantom balance with nothing behind it.
    """

    def setUp(self):
        self.creator = User.objects.create_user(username='treasurer', is_staff=True)
        self.wallet_a = Wallet.objects.create(name='Wallet A', kind='CASH')
        self.wallet_b = Wallet.objects.create(name='Wallet B', kind='BANK')

    def _make_transfer(self, nominal=Decimal('100000')):
        return WalletTransfer.objects.create(
            from_wallet=self.wallet_a, to_wallet=self.wallet_b, nominal=nominal,
            occurred_at=timezone.now(), creator=self.creator,
        )

    def _reload_legs(self, transfer):
        # Deliberately re-fetch from the DB (via with_deleted(), since a leg
        # under test may already be soft-deleted) rather than use the cached
        # transfer.out_transaction/in_transaction attributes, matching how a
        # real caller (e.g. the admin, loading a Transaction by id) would.
        return (
            Transaction.objects.with_deleted().get(pk=transfer.out_transaction_id),
            Transaction.objects.with_deleted().get(pk=transfer.in_transaction_id),
        )

    # -- creation sets transfer_id on both legs, and keeps it in sync in-memory --

    def test_creating_transfer_tags_both_legs_in_db(self):
        transfer = self._make_transfer()
        out_leg, in_leg = self._reload_legs(transfer)

        self.assertEqual(out_leg.transfer_id, transfer.pk)
        self.assertEqual(in_leg.transfer_id, transfer.pk)

    def test_creating_transfer_keeps_cached_legs_in_sync(self):
        # Regression test: transfer.out_transaction/.in_transaction used to
        # return stale cached objects with transfer_id=None right after
        # creation, because they were cached before the bulk .update() that
        # actually sets transfer_id ran.
        transfer = self._make_transfer()

        self.assertEqual(transfer.out_transaction.transfer_id, transfer.pk)
        self.assertEqual(transfer.in_transaction.transfer_id, transfer.pk)

    # -- WalletTransfer.delete() / force_delete() cascade to both legs --

    def test_transfer_delete_soft_deletes_both_legs(self):
        transfer = self._make_transfer()

        transfer.delete()

        out_leg, in_leg = self._reload_legs(transfer)
        self.assertIsNotNone(transfer.deleted_at)
        self.assertIsNotNone(out_leg.deleted_at)
        self.assertIsNotNone(in_leg.deleted_at)

    def test_transfer_delete_excludes_legs_from_default_manager(self):
        transfer = self._make_transfer()
        out_id, in_id = transfer.out_transaction_id, transfer.in_transaction_id

        transfer.delete()

        self.assertFalse(Transaction.objects.filter(pk__in=[out_id, in_id]).exists())
        self.assertEqual(Transaction.objects.with_deleted().filter(pk__in=[out_id, in_id]).count(), 2)

    def test_transfer_force_delete_purges_both_legs(self):
        transfer = self._make_transfer()
        out_id, in_id = transfer.out_transaction_id, transfer.in_transaction_id

        transfer.force_delete()

        self.assertFalse(WalletTransfer.objects.with_deleted().filter(pk=transfer.pk).exists())
        self.assertFalse(Transaction.objects.with_deleted().filter(pk__in=[out_id, in_id]).exists())

    def test_transfer_delete_only_affects_its_own_legs(self):
        transfer1 = self._make_transfer()
        transfer2 = self._make_transfer()

        transfer1.delete()

        out2, in2 = self._reload_legs(transfer2)
        self.assertIsNone(out2.deleted_at)
        self.assertIsNone(in2.deleted_at)
        transfer2.refresh_from_db()
        self.assertIsNone(transfer2.deleted_at)

    # -- deleting a leg directly must cascade back to the sibling + transfer --
    # (this is the exact production bug: transfer #12's OUT leg was deleted
    # this way, without its IN leg or the transfer following along)

    def test_soft_deleting_one_leg_directly_cascades_to_sibling_and_transfer(self):
        transfer = self._make_transfer()
        out_leg, in_leg = self._reload_legs(transfer)

        out_leg.delete()

        transfer.refresh_from_db()
        in_leg.refresh_from_db()
        self.assertIsNotNone(out_leg.deleted_at)
        self.assertIsNotNone(transfer.deleted_at)
        self.assertIsNotNone(in_leg.deleted_at)

    def test_soft_deleting_the_other_leg_also_cascades(self):
        transfer = self._make_transfer()
        out_leg, in_leg = self._reload_legs(transfer)

        in_leg.delete()

        transfer.refresh_from_db()
        out_leg.refresh_from_db()
        self.assertIsNotNone(in_leg.deleted_at)
        self.assertIsNotNone(transfer.deleted_at)
        self.assertIsNotNone(out_leg.deleted_at)

    def test_force_deleting_one_leg_directly_cascades_to_sibling_and_transfer(self):
        transfer = self._make_transfer()
        out_leg, in_leg = self._reload_legs(transfer)

        out_leg.force_delete()

        self.assertFalse(WalletTransfer.objects.with_deleted().filter(pk=transfer.pk).exists())
        self.assertFalse(Transaction.objects.with_deleted().filter(pk__in=[out_leg.pk, in_leg.pk]).exists())

    def test_deleting_one_leg_does_not_affect_an_unrelated_transfer(self):
        transfer1 = self._make_transfer()
        transfer2 = self._make_transfer()
        out_leg1, _ = self._reload_legs(transfer1)

        out_leg1.delete()

        transfer2.refresh_from_db()
        out2, in2 = self._reload_legs(transfer2)
        self.assertIsNone(transfer2.deleted_at)
        self.assertIsNone(out2.deleted_at)
        self.assertIsNone(in2.deleted_at)

    def test_deleting_already_deleted_leg_is_idempotent(self):
        transfer = self._make_transfer()
        out_leg, _ = self._reload_legs(transfer)
        out_leg.delete()
        out_leg.refresh_from_db()

        out_leg.delete()  # should not raise on a second call

        transfer.refresh_from_db()
        self.assertIsNotNone(transfer.deleted_at)

    # -- transfer legs carry no items by design, but cascade must not choke if one exists --

    def test_transfer_delete_also_soft_deletes_a_stray_item_on_a_leg(self):
        transfer = self._make_transfer()
        fund = Fund.objects.create(name='Stray Fund', kind=Fund.Kind.ROUTINE)
        stray_item = TransactionItem.objects.create(
            transaction=transfer.out_transaction, fund=fund, nominal=Decimal('100000'),
        )

        transfer.delete()

        stray_item.refresh_from_db()
        self.assertIsNotNone(stray_item.deleted_at)


class WalletTransferRestoreTests(TestCase):
    """WalletTransfer.restore() must cascade to both legs, mirroring delete()/
    force_delete() — and restoring one leg directly must restore its sibling
    + the transfer, same as deleting one leg cascades the other way.
    """

    def setUp(self):
        self.creator = User.objects.create_user(username='treasurer', is_staff=True)
        self.wallet_a = Wallet.objects.create(name='Wallet A', kind='CASH')
        self.wallet_b = Wallet.objects.create(name='Wallet B', kind='BANK')

    def _make_transfer(self, nominal=Decimal('100000')):
        return WalletTransfer.objects.create(
            from_wallet=self.wallet_a, to_wallet=self.wallet_b, nominal=nominal,
            occurred_at=timezone.now(), creator=self.creator,
        )

    def _reload_legs(self, transfer):
        return (
            Transaction.objects.with_deleted().get(pk=transfer.out_transaction_id),
            Transaction.objects.with_deleted().get(pk=transfer.in_transaction_id),
        )

    # -- WalletTransfer.restore() cascades to both legs --

    def test_transfer_restore_restores_both_legs(self):
        transfer = self._make_transfer()
        transfer.delete()

        transfer.restore()

        out_leg, in_leg = self._reload_legs(transfer)
        self.assertIsNone(transfer.deleted_at)
        self.assertIsNone(out_leg.deleted_at)
        self.assertIsNone(in_leg.deleted_at)

    def test_transfer_restore_persists_to_db(self):
        transfer = self._make_transfer()
        transfer.delete()

        transfer.restore()

        transfer.refresh_from_db()
        out_leg, in_leg = self._reload_legs(transfer)
        self.assertIsNone(transfer.deleted_at)
        self.assertIsNone(out_leg.deleted_at)
        self.assertIsNone(in_leg.deleted_at)

    def test_transfer_restore_makes_legs_visible_in_default_manager(self):
        transfer = self._make_transfer()
        out_id, in_id = transfer.out_transaction_id, transfer.in_transaction_id
        transfer.delete()
        self.assertFalse(Transaction.objects.filter(pk__in=[out_id, in_id]).exists())

        transfer.restore()

        self.assertEqual(Transaction.objects.filter(pk__in=[out_id, in_id]).count(), 2)

    def test_transfer_restore_only_affects_its_own_legs(self):
        transfer1 = self._make_transfer()
        transfer2 = self._make_transfer()
        transfer1.delete()
        transfer2.delete()

        transfer1.restore()

        out2, in2 = self._reload_legs(transfer2)
        self.assertIsNotNone(out2.deleted_at)
        self.assertIsNotNone(in2.deleted_at)
        transfer2.refresh_from_db()
        self.assertIsNotNone(transfer2.deleted_at)

    def test_transfer_restore_on_never_deleted_transfer_is_a_noop(self):
        transfer = self._make_transfer()

        transfer.restore()  # should not raise

        out_leg, in_leg = self._reload_legs(transfer)
        self.assertIsNone(transfer.deleted_at)
        self.assertIsNone(out_leg.deleted_at)
        self.assertIsNone(in_leg.deleted_at)

    def test_transfer_restore_called_twice_is_idempotent(self):
        transfer = self._make_transfer()
        transfer.delete()

        transfer.restore()
        transfer.restore()

        transfer.refresh_from_db()
        self.assertIsNone(transfer.deleted_at)

    # -- restoring one leg directly must cascade to the sibling + transfer --
    # (mirrors deleting one leg directly, which cascades the other way —
    # see test_soft_deleting_one_leg_directly_cascades_to_sibling_and_transfer)

    def test_restoring_one_leg_directly_restores_sibling_and_transfer(self):
        transfer = self._make_transfer()
        transfer.delete()
        out_leg, _ = self._reload_legs(transfer)

        out_leg.restore()

        transfer.refresh_from_db()
        _, in_leg = self._reload_legs(transfer)
        self.assertIsNone(out_leg.deleted_at)
        self.assertIsNone(transfer.deleted_at)
        self.assertIsNone(in_leg.deleted_at)

    def test_restoring_the_other_leg_also_cascades(self):
        transfer = self._make_transfer()
        transfer.delete()
        _, in_leg = self._reload_legs(transfer)

        in_leg.restore()

        transfer.refresh_from_db()
        out_leg, _ = self._reload_legs(transfer)
        self.assertIsNone(in_leg.deleted_at)
        self.assertIsNone(transfer.deleted_at)
        self.assertIsNone(out_leg.deleted_at)

    def test_restoring_one_leg_does_not_affect_an_unrelated_transfer(self):
        transfer1 = self._make_transfer()
        transfer2 = self._make_transfer()
        transfer1.delete()
        transfer2.delete()
        out_leg1, _ = self._reload_legs(transfer1)

        out_leg1.restore()

        transfer2.refresh_from_db()
        out2, in2 = self._reload_legs(transfer2)
        self.assertIsNotNone(transfer2.deleted_at)
        self.assertIsNotNone(out2.deleted_at)
        self.assertIsNotNone(in2.deleted_at)

    def test_restoring_already_active_leg_is_idempotent(self):
        transfer = self._make_transfer()
        transfer.delete()
        out_leg, _ = self._reload_legs(transfer)
        out_leg.restore()
        out_leg.refresh_from_db()

        out_leg.restore()  # should not raise on a second call

        transfer.refresh_from_db()
        self.assertIsNone(transfer.deleted_at)

    # -- restoring a transfer also restores stray items on its legs --

    def test_transfer_restore_also_restores_a_stray_item_on_a_leg(self):
        transfer = self._make_transfer()
        fund = Fund.objects.create(name='Stray Fund', kind=Fund.Kind.ROUTINE)
        stray_item = TransactionItem.objects.create(
            transaction=transfer.out_transaction, fund=fund, nominal=Decimal('100000'),
        )
        transfer.delete()

        transfer.restore()

        stray_item.refresh_from_db()
        self.assertIsNone(stray_item.deleted_at)
