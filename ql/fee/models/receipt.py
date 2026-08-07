from django.conf import settings
from django.db import models
from django.db.models.fields.files import ImageFieldFile
from django.utils import timezone

from .base import TimestampMixin
from ..services.storage import STORAGE_LOCAL, STORAGE_R2, get_receipt_storage, storage_for_backend

_STORAGE_CHOICES = [
    (STORAGE_LOCAL, 'Local'),
    (STORAGE_R2,    'Cloudflare R2'),
]


def _receipt_upload_to(instance, filename):
    month = timezone.now().strftime('%Y/%m')
    return f'receipts/user_{instance.user_id}/{month}/{filename}'


class ReceiptImageFieldFile(ImageFieldFile):
    """A FieldFile whose storage is resolved per-row from receipt_storage,
    instead of the single storage every other FileField is stuck with.
    Reads/writes always go to wherever *this* receipt's file actually lives —
    so flipping settings.STORAGE_BACKEND only changes where *new* receipts
    land, and never orphans receipts already sitting on the other backend.
    """

    def _get_storage(self):
        backend = getattr(self.instance, 'receipt_storage', STORAGE_LOCAL)
        return storage_for_backend(backend)

    def _set_storage(self, value):
        # FieldFile.__init__ unconditionally does self.storage = field.storage;
        # swallow that — our getter resolves dynamically instead.
        pass

    storage = property(_get_storage, _set_storage)


class ReceiptImageField(models.ImageField):
    attr_class = ReceiptImageFieldFile


class Receipt(TimestampMixin):
    # Denormalised for the upload_to path — set before saving the file.
    user         = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='users',
    )
    # storage=get_receipt_storage is only a fallback (used for e.g. field
    # deconstruction) — actual reads/writes go through ReceiptImageFieldFile's
    # per-row dynamic resolution above.
    image           = ReceiptImageField(upload_to=_receipt_upload_to, storage=get_receipt_storage, null=True, blank=True)
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
            # Must be set BEFORE compress_image_field() — it calls
            # image.save(..., save=False) internally, which writes the file
            # through ReceiptImageFieldFile.storage right away, and that
            # reads receipt_storage to pick the backend. Setting it after
            # the write would target wherever the field last pointed.
            self.receipt_storage = getattr(settings, 'STORAGE_BACKEND', STORAGE_LOCAL)
            from ..services.utils import compress_image_field
            compress_image_field(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Receipt #{self.pk}'
