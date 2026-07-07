from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError

from .base import TimestampMixin


class CashEntry(TimestampMixin):
    class Direction(models.TextChoices):
        IN  = 'IN',  'Income'
        OUT = 'OUT', 'Expense'

    fund        = models.ForeignKey('Fund', on_delete=models.PROTECT, related_name='entries')
    direction   = models.CharField(max_length=3, choices=Direction)
    amount      = models.DecimalField(max_digits=15, decimal_places=2)
    occurred_at = models.DateTimeField()
    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='cash_entries',
        help_text='Contributor for IN; responsible person for OUT.',
    )
    category    = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, default='')
    creator     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_entries')

    class Meta:
        app_label = 'ql'
        db_table = 'cash_entries'
        verbose_name_plural = 'Cash entries'
        ordering = ['-occurred_at']
        indexes  = [
            models.Index(fields=['fund', 'direction']),
            models.Index(fields=['occurred_at']),
        ]

    def clean(self):
        if self.direction == self.Direction.IN and self.user_id is None:
            raise ValidationError('user is required for IN cash entries (contributor must be recorded).')

    def __str__(self):
        return f'{self.direction} | {self.fund} | {self.amount:,} | {self.occurred_at:%Y-%m-%d}'
