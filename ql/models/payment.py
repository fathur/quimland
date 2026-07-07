from datetime import date

from django.db import models
from django.db.models import Q

class Payment(models.Model):
    class Kind(models.TextChoices):
        MONTHLY = 'MONTHLY', 'Monthly iuran'
        GARBAGE = 'GARBAGE', 'Garbage iuran'

    batch   = models.ForeignKey('PaymentBatch', on_delete=models.PROTECT, related_name='payments')
    kind    = models.CharField(max_length=10, choices=Kind)
    period  = models.CharField(max_length=7)   # YYYY-MM
    nominal = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        app_label = 'ql'
        db_table = 'payments'
        ordering = ['period']
        indexes  = [
            models.Index(fields=['kind', 'period']),
            models.Index(fields=['batch']),
        ]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        if is_new:
            self._fill_nominal_from_tariff()

        super().save(*args, **kwargs)

    def _fill_nominal_from_tariff(self):
        from .tariff import Tariff

        if self.nominal is not None:
            return

        try:
            period_date = date(int(self.period[:4]), int(self.period[5:7]), 1)
        except (ValueError, IndexError):
            return

        end_of_year = date(date.today().year, 12, 31)

        tariffs = (
            Tariff.objects
            .filter(user=self.batch.user, kind=self.kind, start_from__lte=period_date)
            .filter(Q(end_to__isnull=False, end_to__gte=period_date) | Q(end_to__isnull=True))
            .order_by('-start_from')
        )
        # null end_to means "active through end of this year" — exclude if period is beyond that
        if period_date > end_of_year:
            tariffs = tariffs.filter(end_to__isnull=False)

        tariff = tariffs.first()
        if tariff:
            self.nominal = tariff.nominal
            # self.save(update_fields=['nominal'])

    def __str__(self):
        return f'{self.kind} {self.period} | {self.nominal:,}'
