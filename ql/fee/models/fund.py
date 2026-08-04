from django.db import models
from mptt.managers import TreeManager
from mptt.models import MPTTModel, TreeForeignKey
from mptt.querysets import TreeQuerySet

from .base import SoftDeleteQuerySet, TimestampMixin


class FundQuerySet(SoftDeleteQuerySet, TreeQuerySet):
    pass


class FundTreeManager(TreeManager.from_queryset(FundQuerySet)):
    """Tree-aware manager that also hides soft-deleted funds by default."""

    def get_queryset(self, *args, **kwargs):
        return super().get_queryset(*args, **kwargs).filter(deleted_at__isnull=True)

    def with_deleted(self):
        return super().get_queryset()

    def deleted_only(self):
        return super().get_queryset().filter(deleted_at__isnull=False)


class Fund(MPTTModel, TimestampMixin):
    class Kind(models.TextChoices):
        # GENERAL   = 'GENERAL',   'General (Kas RT)'
        # GARBAGE   = 'GARBAGE',   'Garbage (pass-through)'
        EARMARKED = 'EARMARKED', 'Earmarked'
        ROUTINE = 'ROUTINE', 'Routine'

    class Status(models.TextChoices):
        OPEN   = 'OPEN',   'Open'
        CLOSED = 'CLOSED', 'Closed'

    parent        = TreeForeignKey(
        'self', on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='children',
        help_text='Parent fund for sub-fund reporting hierarchy. Child funds share the parent pool (not ring-fenced).',
    )
    name          = models.CharField(max_length=255)
    color         = models.CharField(max_length=20, default='#6b7280', blank=True, help_text='Hex color used in the dashboard badges, e.g. #22c55e')
    kind          = models.CharField(max_length=10, choices=Kind)
    description   = models.TextField(blank=True, default='')
    target_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    status        = models.CharField(max_length=10, choices=Status, default=Status.OPEN)

    objects = FundTreeManager()

    class MPTTMeta:
        order_insertion_by = ['name']

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

        amount = self.target_amount / len(occupied_user_ids) if occupied_user_ids and self.target_amount is not None else 0

        FundDue.objects.bulk_create([
            FundDue(fund=self, user_id=uid, expected_amount=amount)
            for uid in occupied_user_ids
        ])

    def __str__(self):
        return f'{self.name}'
