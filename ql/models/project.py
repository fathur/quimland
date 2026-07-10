from django.conf import settings
from django.db import models

from .base import TimestampMixin


class Project(TimestampMixin):
    fund    = models.OneToOneField('Fund', on_delete=models.PROTECT, related_name='project')
    pic     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='projects',
        help_text='Person in charge responsible for the project end-to-end.',
    )
    pic_fee = models.DecimalField(
        max_digits=15, decimal_places=2,
        help_text='Agreed PIC compensation. Auto-creates a FEE_PAYABLE Loan on save.',
    )

    class Meta:
        db_table = 'projects'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self._create_pic_fee_loan()

    def _create_pic_fee_loan(self):
        from .loan import Loan
        from django.utils import timezone

        Loan.objects.create(
            fund=self.fund,
            lender=self.pic,
            kind=Loan.Kind.FEE_PAYABLE,
            principal=self.pic_fee,
            borrowed_at=timezone.now().date(),
        )

    def __str__(self):
        return f'Project | {self.fund}'
