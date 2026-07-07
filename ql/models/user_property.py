from django.conf import settings
from django.db import models

from .base import TimestampMixin


class UserProperty(TimestampMixin):
    class OccupancyStatus(models.TextChoices):
        OCCUPIED = 'OCCUPIED', 'Occupied'
        VACANT   = 'VACANT',   'Vacant'
        RENT   = 'RENT',   'Rented'

    user             = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='properties')
    occupancy_status = models.CharField(max_length=10, choices=OccupancyStatus)
    home_number      = models.CharField(max_length=5, blank=True, default='')
    phone            = models.CharField(max_length=20, blank=True, default='', help_text='Include country code, e.g. +628123456789')

    class Meta:
        db_table = 'user_properties'

    def __str__(self):
        return f'{self.user} | {self.occupancy_status}'
