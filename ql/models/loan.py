from django.conf import settings
from django.db import models

from .base import TimestampMixin


class Loan(TimestampMixin):
    class Kind(models.TextChoices):
        CASH_ADVANCE = 'CASH_ADVANCE', 'Cash Advance (shortfall)'
        FEE_PAYABLE  = 'FEE_PAYABLE',  'Fee Payable (PIC fee)'

    class Status(models.TextChoices):
        OPEN   = 'OPEN',   'Open'
        REPAID = 'REPAID', 'Repaid'

    fund        = models.ForeignKey('Fund', on_delete=models.PROTECT, related_name='loans')
    lender      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='loans_given',
    )
    kind        = models.CharField(max_length=20, choices=Kind)
    principal   = models.DecimalField(max_digits=15, decimal_places=2)
    borrowed_at = models.DateField()
    status      = models.CharField(max_length=10, choices=Status, default=Status.OPEN)
    note        = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'loans'
        indexes  = [
            models.Index(fields=['fund', 'status']),
            models.Index(fields=['lender']),
        ]

    def __str__(self):
        return f'{self.kind} | {self.fund} | {self.principal:,} | {self.status}'
