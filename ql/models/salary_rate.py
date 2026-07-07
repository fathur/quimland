import datetime

from django.db import models
from django.core.exceptions import ValidationError


class SalaryRate(models.Model):
    class Payee(models.TextChoices):
        SECURITY = 'SECURITY', 'Security Guard'

    payee      = models.CharField(max_length=20, choices=Payee, default=Payee.SECURITY)
    amount     = models.DecimalField(max_digits=15, decimal_places=2)
    start_from = models.DateField()
    end_to     = models.DateField(null=True, blank=True)  # NULL = currently active

    class Meta:
        db_table = 'salary_rates'
        ordering = ['start_from']

    def clean(self):
        if self.end_to and self.end_to < self.start_from:
            raise ValidationError('end_to must be on or after start_from.')
        # Overlap check (DB-level exclusion constraint added via migration RunSQL)
        qs = SalaryRate.objects.filter(payee=self.payee)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        for other in qs:
            other_end = other.end_to or datetime.date(9999, 12, 31)
            self_end  = self.end_to  or datetime.date(9999, 12, 31)
            if self.start_from <= other_end and self_end >= other.start_from:
                raise ValidationError('Salary rate overlaps with an existing record.')

    def __str__(self):
        end = self.end_to or 'present'
        return f'{self.payee}: {self.amount:,} ({self.start_from} – {end})'
