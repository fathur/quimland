from django.db import models

from .base import TimestampMixin


class TransactionItem(TimestampMixin):
    class Direction(models.TextChoices):
        IN  = 'IN',  'Income'
        OUT = 'OUT', 'Expense'

    transaction = models.ForeignKey('Transaction', on_delete=models.CASCADE, related_name='items')
    fund        = models.ForeignKey('Fund', on_delete=models.PROTECT, related_name='transaction_items')
    # Only set for TRANSFER transactions to override the parent direction per leg.
    # For IN/OUT transactions this must be null — direction is inherited from Transaction.
    direction   = models.CharField(max_length=3, choices=Direction, null=True, blank=True)
    nominal     = models.DecimalField(max_digits=15, decimal_places=2)
    # Tags this leg as a loan disbursement or repayment.
    loan        = models.ForeignKey(
        'Loan', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transaction_items',
    )

    class Meta:
        db_table = 'transaction_items'
        indexes  = [
            models.Index(fields=['transaction']),
            models.Index(fields=['fund']),
        ]

    def effective_direction(self):
        if self.direction:
            return self.direction
        return self.transaction.direction

    def __str__(self):
        return f'Item #{self.pk} | {self.fund} | {self.nominal:,}'
