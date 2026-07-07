from django.conf import settings
from django.db import models


class PaymentBatch(models.Model):
    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payment_batches')
    paid_at = models.DateTimeField()
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_batches')
    note    = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'payment_batches'
        verbose_name_plural = 'Payment batches'
        ordering = ['-paid_at']
        indexes  = [
            models.Index(fields=['user']),
            models.Index(fields=['paid_at']),
        ]

    def __str__(self):
        return f'Batch #{self.pk} | {self.user} | {self.paid_at:%Y-%m-%d}'
