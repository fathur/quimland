from django.db import models

from .base import TimestampMixin


class Fund(TimestampMixin):
    class Kind(models.TextChoices):
        GENERAL   = 'GENERAL',   'General (Kas RT)'
        GARBAGE   = 'GARBAGE',   'Garbage (pass-through)'
        EARMARKED = 'EARMARKED', 'Earmarked'

    class Status(models.TextChoices):
        OPEN   = 'OPEN',   'Open'
        CLOSED = 'CLOSED', 'Closed'

    parent        = models.ForeignKey(
        'self', on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='children',
        help_text='Parent fund for sub-fund reporting hierarchy. Child funds share the parent pool (not ring-fenced).',
    )
    name          = models.CharField(max_length=255)
    kind          = models.CharField(max_length=10, choices=Kind)
    description   = models.TextField(blank=True, default='')
    target_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    status        = models.CharField(max_length=10, choices=Status, default=Status.OPEN)

    class Meta:
        db_table = 'funds'
        constraints = [
            # Only one GENERAL fund and one GARBAGE fund may ever exist.
            models.UniqueConstraint(
                fields=['kind'],
                condition=models.Q(kind='GENERAL'),
                name='fund_unique_general',
            ),
            models.UniqueConstraint(
                fields=['kind'],
                condition=models.Q(kind='GARBAGE'),
                name='fund_unique_garbage',
            ),
        ]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self._create_fund_dues_for_occupied_users()

    def _create_fund_dues_for_occupied_users(self):
        from .user_property import UserProperty
        from .fund_due import FundDue

        if self.kind != Fund.Kind.EARMARKED:
            return

        occupied_user_ids = UserProperty.objects.filter(
            occupancy_status=UserProperty.OccupancyStatus.OCCUPIED
        ).values_list('user_id', flat=True)

        amount = self.target_amount / len(occupied_user_ids) if occupied_user_ids else 0

        FundDue.objects.bulk_create([
            FundDue(fund=self, user_id=uid, expected_amount=amount)
            for uid in occupied_user_ids
        ])

    def __str__(self):
        return f'{self.name} ({self.kind})'
