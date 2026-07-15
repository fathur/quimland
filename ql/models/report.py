from django.conf import settings
from django.db import models
from django.utils import timezone

from .base import TimestampMixin
from ..storage import get_report_storage


def _report_upload_to(instance, filename):
    month = timezone.now().strftime('%Y/%m')
    return f'reports/{month}/{filename}'


class Report(TimestampMixin):
    class Status(models.TextChoices):
        PROCESSING = 'PROCESSING', 'Processing'
        DRAFT      = 'DRAFT',      'Draft'
        DONE       = 'DONE',       'Done'

    fund = models.ForeignKey(
        'Fund', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='reports',
        help_text='The fund this report is associated with.',
    )

    title = models.CharField(max_length=255, blank=True, default='', help_text='Human-readable report title.')

    file = models.FileField(
        upload_to=_report_upload_to, storage=get_report_storage,
        blank=True, help_text='The generated PDF, rendered from content.',
    )

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_reports',
        help_text='The user who created this report.',
    )

    status = models.CharField(max_length=10, choices=Status, default=Status.PROCESSING)
    completed_at = models.DateTimeField(null=True, blank=True, help_text='When the PDF was generated from content.')

    content = models.TextField(blank=True, default='', help_text='Report body in Markdown. Editable before PDF generation.')

    class Meta:
        db_table = 'reports'

    def __str__(self):
        return self.title or f'Report #{self.pk}'
