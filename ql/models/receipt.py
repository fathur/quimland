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


class Receipt(TimestampMixin):
    # Denormalised for the upload_to path — set before saving the file.
    user         = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='users',
    )
    image           = models.ImageField(upload_to=_receipt_upload_to, storage=get_receipt_storage, null=True, blank=True)
    receipt_storage = models.CharField(
        max_length=10,
        choices=_STORAGE_CHOICES,
        default=STORAGE_LOCAL,
        editable=False,
        help_text='Backend that holds the receipt file.',
    )

    class Meta:
        db_table = 'receipts'

    def save(self, *args, **kwargs):
        if self.image and not self.image._committed:
            from ..utils import compress_image_field
            compress_image_field(self.image)
            self.receipt_storage = getattr(settings, 'STORAGE_BACKEND', STORAGE_LOCAL)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Receipt #{self.pk}'
