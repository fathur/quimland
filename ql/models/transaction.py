from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from .base import TimestampMixin


class Transaction(TimestampMixin):
    class Direction(models.TextChoices):
        IN       = 'IN',       'Income'
        OUT      = 'OUT',      'Expense'
        TRANSFER = 'TRANSFER', 'Internal Transfer'

    direction   = models.CharField(max_length=10, choices=Direction)
    nominal     = models.DecimalField(max_digits=15, decimal_places=2)
    occurred_at = models.DateTimeField(null=True, blank=True)
    receipt   = models.OneToOneField(
        'Receipt', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transaction',
    )
    # resident/contributor (IN) or PIC/responsible person (OUT/TRANSFER)
    user      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='transactions',
    )
    # always the treasurer who actually enters the record
    creator   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='created_transactions',
    )
    note      = models.TextField(blank=True, default='')
    wallet = models.ForeignKey(
        'Wallet', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transactions',
    )
    # Set when this transaction is one of the two legs of an internal wallet
    # transfer. Transfer legs stay IN/OUT so the wallet dashboard debits/credits
    # correctly, but carry this marker so income/expense reports can exclude them.
    transfer = models.ForeignKey(
        'WalletTransfer', on_delete=models.CASCADE,
        null=True, blank=True, editable=False,
        related_name='legs',
    )
    class Highlight(models.TextChoices):
        NONE    = '',        'None'
        WARNING = 'warning', 'Warning'
        DANGER  = 'danger',  'Danger'

    highlight = models.CharField(max_length=10, choices=Highlight, blank=True, default='')

    # Polymorphic attachments (e.g. shopping proof for expenses). Reverse side
    # of Asset's GenericForeignKey; lets a transaction hold many proof files
    # and cascade-deletes them with the transaction.
    assets = GenericRelation('Asset', related_query_name='transaction')

    is_qris = models.BooleanField(default=False)

    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['direction']),
            models.Index(fields=['user']),
            models.Index(fields=['creator']),
        ]

    def __str__(self):
        return f'{self.direction} | {self.nominal:,} | {self.created_at:%Y-%m-%d}'


class IncomeTransaction(Transaction):
    class Meta:
        proxy = True
        verbose_name        = 'Income'
        verbose_name_plural = 'Income'


class ExpenseTransaction(Transaction):
    class Meta:
        proxy = True
        verbose_name        = 'Expense'
        verbose_name_plural = 'Expenses'


class TransferTransaction(Transaction):
    class Meta:
        proxy = True
        verbose_name        = 'Transfer'
        verbose_name_plural = 'Transfers'


class AllTransaction(Transaction):
    class Meta:
        proxy = True
        verbose_name        = 'Transaction'
        verbose_name_plural = 'Transactions'
