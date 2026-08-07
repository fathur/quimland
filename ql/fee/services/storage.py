from django.conf import settings
from django.core.files.storage import FileSystemStorage

STORAGE_LOCAL = 'local'
STORAGE_R2    = 'r2'


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
