from django.conf import settings
from django.db import models
from django.utils import timezone

from .base import TimestampMixin
from ..services.storage import (
    STORAGE_BACKEND_CHOICES,
    STORAGE_LOCAL,
    DynamicStorageImageField,
    get_receipt_storage,
)


class DueNote(TimestampMixin):
    """Explains why a routine due (user, fund, period) hasn't been paid.

    Exists independently of any Transaction/TransactionItem — it annotates the
    *absence* of a payment (the red cells in the payments dashboard). It is only
    ever rendered while the cell is unpaid; once the payment lands the badge goes
    green and the note simply stops showing. No 'resolved' flag needed.
    """

    class Reason(models.TextChoices):
        NOT_BILLED = 'NOT_BILLED', 'Belum ditagih'
        PROMISED   = 'PROMISED',   'Janji bayar'
        PAID_CASH  = 'PAID_CASH',  'Sudah bayar (belum dicatat)'
        HARDSHIP   = 'HARDSHIP',   'Kesulitan ekonomi'
        VACANT     = 'VACANT',     'Rumah kosong'
        MOVED      = 'MOVED',      'Pindah / keluar'
        DISPUTE    = 'DISPUTE',    'Keberatan / sengketa'
        OTHER      = 'OTHER',      'Lainnya'

    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='due_notes')
    fund    = models.ForeignKey('Fund', on_delete=models.CASCADE, related_name='due_notes')
    period  = models.CharField(max_length=7, help_text='YYYY-MM')
    reason  = models.CharField(max_length=20, choices=Reason.choices, default=Reason.NOT_BILLED)
    note    = models.TextField(blank=True, default='')
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_due_notes',
    )

    class Meta:
        app_label = 'fee'
        db_table  = 'due_notes'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'fund', 'period'],
                name='due_notes_unique_user_fund_period',
            ),
        ]

    def __str__(self):
        return f'{self.user} — {self.fund} {self.period}: {self.get_reason_display()}'


def _due_note_proof_upload_to(instance, filename):
    month = timezone.now().strftime('%Y/%m')
    return f'due_notes/user_{instance.due_note.user_id}/{month}/{filename}'


class DueNoteProof(TimestampMixin):
    """One image proof attached to a DueNote (a note can have several)."""

    due_note = models.ForeignKey('DueNote', on_delete=models.CASCADE, related_name='proofs')
    # storage=get_receipt_storage is only a fallback (used for e.g. field
    # deconstruction) — actual reads/writes go through DynamicStorageImageField's
    # per-row resolution (keyed off receipt_storage, below).
    image    = DynamicStorageImageField(upload_to=_due_note_proof_upload_to, storage=get_receipt_storage)
    receipt_storage = models.CharField(
        max_length=10,
        choices=STORAGE_BACKEND_CHOICES,
        default=STORAGE_LOCAL,
        editable=False,
        help_text='Backend that holds the proof image.',
    )

    class Meta:
        app_label = 'fee'
        db_table  = 'due_note_proofs'

    def save(self, *args, **kwargs):
        if self.image and not self.image._committed:
            # Must be set before compress_image_field() actually writes the
            # file — see Receipt.save()/Asset.save() for the same reasoning.
            self.receipt_storage = getattr(settings, 'STORAGE_BACKEND', STORAGE_LOCAL)
            from ..services.utils import compress_image_field
            compress_image_field(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Proof #{self.pk} for DueNote #{self.due_note_id}'
