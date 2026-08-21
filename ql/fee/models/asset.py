from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .base import TimestampMixin
from ..services.storage import (
    STORAGE_BACKEND_CHOICES,
    STORAGE_LOCAL,
    DynamicStorageFileField,
    get_asset_storage,
)
from ..services.utils import (
    ALLOWED_ASSET_MIME_TYPES,
    IMAGE_MIME_TYPES,
    compress_image_field,
    detect_asset_mime,
    extract_image_metadata,
)


def _asset_upload_to(instance, filename):
    month = timezone.now().strftime('%Y/%m')
    return f'assets/{month}/{filename}'


class Asset(TimestampMixin):
    """A stored file (or external URL) that can be attached to any model.

    Attachment is polymorphic via a direct GenericForeignKey: many Asset rows
    may point at the same owner (e.g. several shopping-proof files on one
    expense Transaction). Either ``file`` OR ``url`` is set, never both.
    """

    id = models.BigAutoField(primary_key=True)

    # ── Polymorphic owner (optional; an asset may be uploaded before linking) ──
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='assets',
    )
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Distinguishes what the attachment is for on a given owner,
    # e.g. 'expense_proof'. Free-form, optional.
    purpose = models.CharField(max_length=50, blank=True, default='')

    # ── Payload: exactly one of file / url ────────────────────────────────────
    # storage=get_asset_storage is only a fallback (used for e.g. field
    # deconstruction) — actual reads/writes go through DynamicStorageFileField's
    # per-row resolution (keyed off the `storage` column, below).
    file = DynamicStorageFileField(
        upload_to=_asset_upload_to, storage=get_asset_storage,
        null=True, blank=True,
    )
    url = models.URLField(
        max_length=1000, null=True, blank=True,
        help_text='External URL, used as a fallback when the file is too large to upload.',
    )

    # ── Descriptive metadata (auto-filled for uploads) ────────────────────────
    original_name = models.CharField(max_length=255, blank=True, default='')
    mime_type     = models.CharField(max_length=100, blank=True, default='')
    size          = models.BigIntegerField(null=True, blank=True)  # bytes
    metadata      = models.JSONField(default=dict, blank=True)

    storage = models.CharField(
        max_length=10,
        choices=STORAGE_BACKEND_CHOICES,
        default=STORAGE_LOCAL,
        editable=False,
        help_text='Backend that holds the asset file.',
    )

    class Meta:
        db_table = 'assets'
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['mime_type']),
        ]
        constraints = [
            # Exactly one payload: a non-empty file with no url, or a url with
            # no file. (FileField stores '' when empty, not NULL.)
            models.CheckConstraint(
                name='asset_file_xor_url',
                condition=(
                    (~models.Q(file='') & models.Q(url__isnull=True))
                    | (models.Q(file='') & models.Q(url__isnull=False))
                ),
            ),
        ]

    def __str__(self):
        return self.original_name or self.url or f'Asset #{self.pk}'

    @property
    def file_extension(self):
        """Uppercase file extension (e.g. 'PDF'), or '' if there isn't one."""
        name = self.original_name or (self.file.name if self.file else '')
        return name.rsplit('.', 1)[-1].upper() if '.' in name else ''

    # ── Validation ────────────────────────────────────────────────────────────
    def clean(self):
        super().clean()
        has_file = bool(self.file)
        has_url = bool(self.url)
        if has_file == has_url:
            raise ValidationError(
                'Provide either a file OR a URL — not both, and not neither.'
            )

        if has_file and not self.file._committed:
            self._validate_upload()

    def _validate_upload(self):
        """Sniff type, enforce allow-list and size cap on an uncommitted file."""
        f = self.file.file
        mime = detect_asset_mime(f, filename=self.file.name)
        if mime not in ALLOWED_ASSET_MIME_TYPES:
            allowed = ', '.join(
                ext for exts in ALLOWED_ASSET_MIME_TYPES.values() for ext in exts
            )
            raise ValidationError(
                f'Unsupported file type ({mime}). Allowed: {allowed}.'
            )

        size = getattr(self.file, 'size', None)
        max_size = getattr(settings, 'ASSET_MAX_UPLOAD_SIZE', 10 * 1024 * 1024)
        if size and size > max_size:
            mb = max_size / (1024 * 1024)
            raise ValidationError(
                f'File is too large ({size / (1024 * 1024):.1f} MiB). '
                f'Limit is {mb:.0f} MiB — provide a URL instead.'
            )
        # Stash for save() so we don't sniff twice.
        self._detected_mime = mime

    # ── Persistence ───────────────────────────────────────────────────────────
    def save(self, *args, **kwargs):
        if self.file and not self.file._committed:
            # Must be set before the file is actually written — for image
            # assets that happens via compress_image_field() below; for
            # everything else it happens inside super().save() via
            # FileField.pre_save(). Either way, DynamicStorageFileField reads
            # self.storage to pick the backend, so it must already be
            # correct by the time either write occurs.
            self.storage = getattr(settings, 'STORAGE_BACKEND', STORAGE_LOCAL)

            mime = getattr(self, '_detected_mime', None) or detect_asset_mime(
                self.file.file, filename=self.file.name
            )
            self.mime_type = mime
            if not self.original_name:
                self.original_name = self.file.name.rsplit('/', 1)[-1]

            if mime in IMAGE_MIME_TYPES:
                self.metadata = {**(self.metadata or {}), **extract_image_metadata(self.file.file)}
                # Compress in place (resize + JPEG). mime_type stays image/*;
                # PNGs become JPEG, so normalise the recorded type.
                compress_image_field(self.file)
                self.mime_type = 'image/jpeg'

            self.size = getattr(self.file, 'size', None)

        elif self.url:
            self.file = None
            if not self.mime_type:
                self.mime_type = 'text/uri-list'

        super().save(*args, **kwargs)
