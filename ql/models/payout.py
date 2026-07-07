from django.conf import settings
from django.db import models


class Payout(models.Model):
    class Payee(models.TextChoices):
        SECURITY   = 'SECURITY',   'Security Guard'
        SANITATION = 'SANITATION', 'Sanitation Worker'

    payee       = models.CharField(max_length=20, choices=Payee)
    period      = models.CharField(max_length=7)   # YYYY-MM
    payout_date = models.DateField()
    amount      = models.DecimalField(max_digits=15, decimal_places=2)
    creator     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_payouts')
    note        = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'payouts'
        ordering = ['payout_date', 'payee']
        indexes  = [
            models.Index(fields=['payee', 'period']),
            models.Index(fields=['payout_date']),
        ]

    def __str__(self):
        return f'{self.payee} | {self.period} | {self.payout_date} | {self.amount:,}'
