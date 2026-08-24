import logging
import os

from celery import shared_task
from django.core.files.base import ContentFile

from ql.fee.models import Asset
from ql.fee.services.utils import (
    VIDEO_RESOLUTION_CHOICES,
    download_field_to_temp,
    extract_video_thumbnail,
    transcode_video,
)

logger = logging.getLogger('ql.fee.tasks.asset_processing')


@shared_task
def process_video_asset(asset_id, resolution):
    """Post-upload processing for a video Asset, run in the background so the
    upload request that created it doesn't block on ffmpeg: always captures
    a grid thumbnail frame, and additionally transcodes the file itself when
    `resolution` isn't 'original'. Runs after the Asset row (with its
    original file) already exists and is marked PROCESSING — see
    ql.fee.admin.asset_manager.upload_view.

    Source video is downloaded to a local temp file once and reused for both
    steps. On a transcode failure the original file is left untouched
    (nothing lost) and the asset is marked FAILED; a missing thumbnail alone
    isn't a failure — the grid just falls back to a plain MP4 badge.
    """
    try:
        asset = Asset.objects.get(pk=asset_id)
    except Asset.DoesNotExist:
        logger.warning('process_video_asset: asset %s no longer exists', asset_id)
        return

    src_path = download_field_to_temp(asset.file, suffix='.mp4')
    update_fields = ['processing_status']
    try:
        thumb_data = extract_video_thumbnail(src_path)
        if thumb_data:
            asset.thumbnail.save(f'{asset.id}-thumb.jpg', ContentFile(thumb_data), save=False)
            update_fields.append('thumbnail')
        else:
            logger.warning('process_video_asset: no thumbnail captured for asset %s', asset_id)

        if resolution in VIDEO_RESOLUTION_CHOICES:
            try:
                new_data = transcode_video(src_path, resolution)
            except RuntimeError:
                logger.exception('process_video_asset: compression failed for asset %s (%s)', asset_id, resolution)
                asset.processing_status = Asset.ProcessingStatus.FAILED
                asset.save(update_fields=update_fields)
                return

            old_name = asset.file.name
            filename = os.path.splitext(os.path.basename(old_name))[0] + f'-{resolution}.mp4'
            asset.file.save(filename, ContentFile(new_data), save=False)
            asset.size = len(new_data)
            update_fields += ['file', 'size']
            if old_name and old_name != asset.file.name:
                asset.file.storage.delete(old_name)
    finally:
        try:
            os.remove(src_path)
        except OSError:
            pass

    asset.processing_status = Asset.ProcessingStatus.READY
    asset.save(update_fields=update_fields)
    logger.info(
        'process_video_asset: asset %s done (resolution=%s, thumbnail=%s)',
        asset_id, resolution, bool(thumb_data),
    )
