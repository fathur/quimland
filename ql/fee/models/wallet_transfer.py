from django.db import models
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ql.fee.models.transaction import Transaction
from ql.fee.models.transaction_item import TransactionItem

from .base import TimestampMixin

class WalletTransfer(TimestampMixin):
    id = models.BigAutoField(primary_key=True)
    from_wallet     = models.ForeignKey('Wallet', on_delete=models.PROTECT, related_name='transfers_out')
    to_wallet       = models.ForeignKey('Wallet', on_delete=models.PROTECT, related_name='transfers_in')
    nominal         = models.DecimalField(max_digits=15, decimal_places=2)
    occurred_at     = models.DateTimeField()
    note            = models.TextField(blank=True, default='')
    creator         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    # CASCADE both ways: a transfer and its two IN/OUT legs are one atomic unit.
    # Deleting the transfer removes both legs (via Transaction.transfer), and
    # deleting a leg removes the transfer. This also avoids a PROTECT/CASCADE
    # cycle that would otherwise block deletion entirely.
    out_transaction = models.OneToOneField('Transaction', on_delete=models.CASCADE, editable=False, related_name='+')
    in_transaction  = models.OneToOneField('Transaction', on_delete=models.CASCADE, editable=False, related_name='+')

    class Meta:
        db_table = 'wallet_transfers'

    def save(self, *args, **kwargs):
        creating = self.pk is None
        if creating:
            with transaction.atomic():
                self.out_transaction = Transaction.objects.create(
                    direction=Transaction.Direction.OUT, wallet=self.from_wallet,
                    nominal=self.nominal, occurred_at=self.occurred_at,
                    user=self.creator, creator=self.creator, note=self.note,
                )
                self.in_transaction = Transaction.objects.create(
                    direction=Transaction.Direction.IN, wallet=self.to_wallet,
                    nominal=self.nominal, occurred_at=self.occurred_at,
                    user=self.creator, creator=self.creator, note=self.note,
                )
                super().save(*args, **kwargs)
                # Now that this transfer has a PK, tag both legs so income/expense
                # reports can exclude them (they stay IN/OUT for wallet balances).
                Transaction.objects.filter(
                    pk__in=[self.out_transaction_id, self.in_transaction_id]
                ).update(transfer=self)
                # Keep the cached in-memory legs (self.out_transaction /
                # self.in_transaction, set above from .create()) in sync with
                # the bulk update — otherwise transfer.out_transaction.transfer_id
                # reads back as None until the leg is reloaded from the DB.
                self.out_transaction.transfer = self
                self.in_transaction.transfer = self
        else:
            with transaction.atomic():
                super().save(*args, **kwargs)

                out_tx = self.out_transaction

                out_tx.occurred_at = self.occurred_at
                out_tx.wallet = self.from_wallet
                out_tx.nominal = self.nominal
                out_tx.note = self.note

                out_tx.save()

                in_tx = self.in_transaction

                in_tx.occurred_at = self.occurred_at
                in_tx.wallet = self.to_wallet
                in_tx.nominal = self.nominal
                in_tx.note = self.note

                in_tx.save()

    def delete(self, using=None, keep_parents=False):
        # Bulk .update() here (not leg.delete()) deliberately bypasses
        # Transaction.delete(), which would otherwise recurse back into this
        # method via self.transfer.delete().
        with transaction.atomic():
            now = timezone.now()
            leg_ids = [self.out_transaction_id, self.in_transaction_id]
            TransactionItem.objects.filter(transaction_id__in=leg_ids).update(deleted_at=now)
            Transaction.objects.filter(pk__in=leg_ids).update(deleted_at=now)
            WalletTransfer.objects.filter(pk=self.pk).update(deleted_at=now)
            self.deleted_at = now

    def force_delete(self, using=None, keep_parents=False):
        with transaction.atomic():
            leg_ids = [self.out_transaction_id, self.in_transaction_id]
            TransactionItem.objects.with_deleted().filter(transaction_id__in=leg_ids).force_delete()
            Transaction.objects.with_deleted().filter(pk__in=leg_ids).force_delete()
            super().force_delete(using=using, keep_parents=keep_parents)

    def restore(self):
        # Bulk .restore() here (not leg.restore()) deliberately bypasses
        # Transaction.restore(), which would otherwise recurse back into this
        # method via self.transfer.restore().
        with transaction.atomic():
            leg_ids = [self.out_transaction_id, self.in_transaction_id]
            TransactionItem.objects.with_deleted().filter(transaction_id__in=leg_ids).restore()
            Transaction.objects.with_deleted().filter(pk__in=leg_ids).restore()
            super().restore()

    def __str__(self):
        return f'Transfer #{self.pk} | {self.from_wallet} → {self.to_wallet} | {self.nominal:,}'