from django.conf import settings
from django.db import models
from django.utils import timezone

from .base import TimestampMixin
from ..storage import get_receipt_storage

STORAGE_LOCAL = 'local'
STORAGE_R2    = 'r2'

_STORAGE_CHOICES = [
    (STORAGE_LOCAL, 'Local'),
    (STORAGE_R2,    'Cloudflare R2'),
]


def _receipt_upload_to(instance, filename):
    month = timezone.now().strftime('%Y/%m')
    return f'receipts/user_{instance.user_id}/{month}/{filename}'


class PaymentBatch(TimestampMixin):
    user            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payment_batches')
    paid_at         = models.DateTimeField()
    creator         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_batches')
    note            = models.TextField(blank=True, default='')
    receipt         = models.ImageField(upload_to=_receipt_upload_to, blank=True, null=True, storage=get_receipt_storage)
    receipt_storage = models.CharField(
        max_length=10,
        choices=_STORAGE_CHOICES,
        default=STORAGE_LOCAL,
        editable=False,
        help_text='Backend that holds the receipt file.',
    )
    nominal         = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    class Meta:
        db_table = 'payment_batches'
        verbose_name_plural = 'Payment batches'
        ordering = ['-paid_at']
        indexes  = [
            models.Index(fields=['user']),
            models.Index(fields=['paid_at']),
        ]

    def save(self, *args, **kwargs):
        if self.receipt and not self.receipt._committed:
            from ..utils import compress_image_field
            compress_image_field(self.receipt)
            self.receipt_storage = getattr(settings, 'STORAGE_BACKEND', STORAGE_LOCAL)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Batch #{self.pk} | {self.user} | {self.paid_at:%Y-%m-%d}'
