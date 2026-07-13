from django.db import models
from django.conf import settings
from django.db import transaction

from ql.models.transaction import Transaction

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
        else:
            super().save(*args, **kwargs)