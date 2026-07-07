from django.conf import settings
from django.db import models


class UserProperty(models.Model):
    class OccupancyStatus(models.TextChoices):
        OCCUPIED = 'OCCUPIED', 'Occupied'
        VACANT   = 'VACANT',   'Vacant'

    user             = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='properties')
    occupancy_status = models.CharField(max_length=10, choices=OccupancyStatus)

    class Meta:
        db_table = 'user_properties'

    def __str__(self):
        return f'{self.user} | {self.occupancy_status}'
