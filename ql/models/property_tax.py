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