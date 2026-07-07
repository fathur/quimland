from django.conf import settings
from django.db import models

from .base import TimestampMixin


class FundDue(TimestampMixin):
    fund            = models.ForeignKey('Fund', on_delete=models.PROTECT, related_name='dues')
    user            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='fund_dues')
    expected_amount = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        app_label = 'ql'
        db_table = 'fund_dues'
        constraints = [
            models.UniqueConstraint(fields=['fund', 'user'], name='fund_dues_unique_fund_user'),
        ]

    def __str__(self):
        return f'{self.user} owes {self.expected_amount:,} to {self.fund}'
