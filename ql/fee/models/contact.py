from django.conf import settings
from django.db import models

from .base import TimestampMixin

class Contact(TimestampMixin):

    class ContactType(models.TextChoices):
        EMAIL = 'EMAIL', 'Email'
        PHONE = 'PHONE', 'Phone'

    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contacts')
    kind        = models.CharField(max_length=100, choices=ContactType)
    value       = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')


    class Meta:
        db_table = 'contacts'

   
    def __str__(self):
        return f'{self.kind}: {self.value} | {self.user}'