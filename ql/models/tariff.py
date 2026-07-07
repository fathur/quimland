from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError

from .base import TimestampMixin


class Tariff(TimestampMixin):
    class Kind(models.TextChoices):
        MONTHLY = 'MONTHLY', 'Monthly iuran'
        GARBAGE = 'GARBAGE', 'Garbage iuran'

    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='tariffs')
    kind       = models.CharField(max_length=10, choices=Kind)
    nominal    = models.DecimalField(max_digits=15, decimal_places=2)
    start_from = models.DateField()
    end_to     = models.DateField(null=True, blank=True)
    note       = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'tariffs'
        ordering = ['user', 'kind', 'start_from']
        indexes  = [models.Index(fields=['user', 'kind'])]

    def clean(self):
        if self.end_to and self.end_to < self.start_from:
            raise ValidationError('end_to must be on or after start_from.')

    def __str__(self):
        return f'{self.user} | {self.kind} | {self.nominal:,} from {self.start_from}'
