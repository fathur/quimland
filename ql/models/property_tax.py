from django.conf import settings
from django.db import models
from django.utils import timezone

from .base import TimestampMixin

from ..storage import get_receipt_storage


def _receipt_upload_to(instance, filename):
    month = timezone.now().strftime('%Y/%m')
    return f'pbb/user_{instance.user_id}/{month}/{filename}'


class PropertyTax(TimestampMixin):

    user       = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='property_tax')
    nop       = models.CharField(max_length=20, blank=True, default='', help_text='Nomor Objek Pajak')
    land_area = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    building_area = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    attachment         = models.ImageField(upload_to=_receipt_upload_to, blank=True, null=True, storage=get_receipt_storage)

    class Meta:
        db_table = 'property_taxes'

    def _compress_attachment(self):
        import os
        import io
        
        from PIL import Image
        from django.core.files.base import ContentFile

        img = Image.open(self.attachment)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        max_dim = 1920
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=85, optimize=True)
        buf.seek(0)

        filename = os.path.splitext(os.path.basename(self.attachment.name))[0] + '.jpg'
        self.attachment.save(filename, ContentFile(buf.read()), save=False)


    def save(self, *args, **kwargs):
        if self.attachment and not self.attachment._committed:
            self._compress_attachment()
        super().save(*args, **kwargs)