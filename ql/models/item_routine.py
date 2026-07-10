from django.db import models

from .base import TimestampMixin


class ItemRoutine(TimestampMixin):
    transaction_item = models.OneToOneField(
        'TransactionItem', on_delete=models.CASCADE,
        related_name='routine',
    )
    # YYYY-MM — replaces the old Payment.kind+period concept
    period = models.CharField(max_length=7)

    class Meta:
        db_table = 'item_routines'
        indexes  = [models.Index(fields=['period'])]

    def __str__(self):
        return f'Routine | {self.transaction_item_id} | {self.period}'
