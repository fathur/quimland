from django.conf import settings
from django.core.files.storage import FileSystemStorage


def get_receipt_storage():
    backend = getattr(settings, 'STORAGE_BACKEND', 'local')
    if backend == 'r2':
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

    return FileSystemStorage()
