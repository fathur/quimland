from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models.fields.files import FieldFile, ImageFieldFile

STORAGE_LOCAL = 'local'
STORAGE_R2    = 'r2'

STORAGE_BACKEND_CHOICES = [
    (STORAGE_LOCAL, 'Local'),
    (STORAGE_R2,    'Cloudflare R2'),
]


def storage_for_backend(backend):
    """Return a Storage instance for the given backend name ('local' or 'r2').

    Used two ways: keyed off the current global STORAGE_BACKEND setting (via
    _get_secure_storage(), below — Asset/Report/PropertyTax/DueNote all work
    this way), and keyed off a specific row's own stored backend value (see
    Receipt.image, which must keep reading/writing wherever *that* receipt's
    file actually lives, independent of whatever STORAGE_BACKEND is today).
    """
    if backend == STORAGE_R2:
        from storages.backends.s3boto3 import S3Boto3Storage

        kwargs = dict(
            bucket_name=settings.R2_BUCKET_NAME,
            endpoint_url=settings.R2_ENDPOINT_URL,
            access_key=settings.R2_ACCESS_KEY_ID,
            secret_key=settings.R2_SECRET_ACCESS_KEY,
            region_name='auto',
            # R2 public buckets don't need query-string auth; presigned URLs
            # are used automatically when custom_domain is not set.
            querystring_auth=not bool(getattr(settings, 'R2_CUSTOM_DOMAIN', '')),
        )
        if getattr(settings, 'R2_CUSTOM_DOMAIN', ''):
            kwargs['custom_domain'] = settings.R2_CUSTOM_DOMAIN
        return S3Boto3Storage(**kwargs)

    # Local: store under SECURE_MEDIA_ROOT, served by the authenticated /secure-media/ view.
    return FileSystemStorage(
        location=settings.SECURE_MEDIA_ROOT,
        base_url='/secure-media/',
    )


def _get_secure_storage():
    """Return the currently configured backend (R2 or local secure filesystem)."""
    return storage_for_backend(getattr(settings, 'STORAGE_BACKEND', STORAGE_LOCAL))


def get_receipt_storage():
    return _get_secure_storage()


def get_asset_storage():
    return _get_secure_storage()


def get_report_storage():
    return _get_secure_storage()


# ── Per-row dynamic storage ───────────────────────────────────────────────
# A model that tracks which backend its file actually lives on (a `storage`
# CharField using STORAGE_BACKEND_CHOICES) uses these instead of a plain
# FileField/ImageField, so that field's storage is resolved per-row from
# that column — not from whatever STORAGE_BACKEND happens to be right now.
# Without this, flipping STORAGE_BACKEND would orphan every file already
# sitting on the other backend, since a plain FileField shares ONE storage
# instance across every row.
#
# Shared by Receipt.image, Asset.file, and DueNoteProof.image.
class _DynamicStorageMixin:
    def _get_storage(self):
        # NOTE: self.instance.storage is the *model's* `storage` CharField
        # (a plain string like 'r2') — unrelated to this property, which is
        # THIS FieldFile's own `.storage` (a Storage backend instance). Same
        # name, different objects; don't confuse the two.
        backend = getattr(self.instance, 'storage', STORAGE_LOCAL)
        return storage_for_backend(backend)

    def _set_storage(self, value):
        # FieldFile.__init__ unconditionally does self.storage = field.storage;
        # swallow that assignment — the getter above resolves it dynamically
        # from the instance instead.
        pass

    storage = property(_get_storage, _set_storage)


class DynamicStorageFieldFile(_DynamicStorageMixin, FieldFile):
    pass


class DynamicStorageImageFieldFile(_DynamicStorageMixin, ImageFieldFile):
    pass


class DynamicStorageFileField(models.FileField):
    attr_class = DynamicStorageFieldFile


class DynamicStorageImageField(models.ImageField):
    attr_class = DynamicStorageImageFieldFile
