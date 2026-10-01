from django.db import models

from ql.common.base import TimestampMixin


class RoutinePayout(TimestampMixin):
    """Allocates part (or all) of an expense item to one routine period of a
    pass-through fund (e.g. garbage collector pay for 2026-08). The item itself
    is recorded normally as an OUT TransactionItem; this row only says which
    month's collected money it settles, so a late/rapel payment can be paid out
    later against the month it belongs to."""

    transaction_item = models.ForeignKey(
        'TransactionItem', on_delete=models.CASCADE,
        related_name='payouts',
    )
    # YYYY-MM — same convention as ItemRoutine.period
    period = models.CharField(max_length=7)
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = 'routine_payouts'
        ordering = ['period', 'created_at']
        indexes  = [models.Index(fields=['period'])]

    def __str__(self):
        return f'Payout | {self.period} | {self.amount:,} | item {self.transaction_item_id}'
