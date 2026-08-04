from django.conf import settings
from django.db import models
from django.utils import timezone

from .base import TimestampMixin

class Wallet(TimestampMixin):
    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=20, choices=[
        ('CASH', 'Cash'),
        ('BANK', 'Bank'),
        ('E-WALLET', 'E-Wallet'),
    ])
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        db_table = 'wallets'
        ordering = ['name']
        

    def __str__(self):
        return f'{self.name} ({self.kind})'