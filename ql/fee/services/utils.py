import io
import os
import re

from django.conf import settings
from django.core.files.base import ContentFile


def normalize_phone(raw):
    """Digits only, keeping a leading '+' if present. A leading '0' is treated
    as the Indonesian trunk prefix and rewritten to '+62'. Mirrors UserProperty.clean()."""
    if raw.startswith('+'):
        return '+' + re.sub(r'\D', '', raw)
    digits = re.sub(r'\D', '', raw)
    if digits.startswith('0'):
        return '+62' + digits[1:]
    return digits


def fmt_rupiah(amount):
    formatted = f'{amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'Rp {formatted}'


def show_toolbar_to_staff(request):
    """SHOW_TOOLBAR_CALLBACK: toolbar visible to logged-in staff/superusers only,
    independent of DEBUG or client IP — safe to enable on the production domain
    without exposing Django's verbose DEBUG error pages to residents.

    Gated by DEBUG_TOOLBAR_ENABLED so the toolbar stays off by default even in
    prod; flip that env var on only while actively debugging.
    """
    if not settings.DEBUG_TOOLBAR_ENABLED:
        return False
    user = getattr(request, 'user', None)
    return bool(user and user.is_active and user.is_staff)


def render_report_markdown(content):
    """Convert report Markdown content to HTML.

    Shared by the browser preview and the PDF template so both always
    render from the exact same pipeline — what the user previews is
    guaranteed to match the generated PDF.
    """
    import markdown

    return markdown.markdown(
        content or '',
        extensions=['tables', 'fenced_code', 'sane_lists'],
    )


def generate_image_thumbnail(image_field, max_dim=320, quality=80):
    """Return small JPEG thumbnail bytes for an ImageField, scaled so its
    longest side is max_dim. Unlike compress_image_field, this doesn't mutate
    image_field in place — it returns bytes for the caller to assign to a
    *different* field (Asset.thumbnail), so the full-size image stays
    available for the detail view; only grid previews use the thumbnail.
    """
    from PIL import Image

    img = Image.open(image_field)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    return buf.getvalue()


def compress_image_field(image_field, max_dim=1920, quality=85):
    """Compress and resize an ImageField in-place before the model is saved."""
    from PIL import Image

    img = Image.open(image_field)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')

    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    buf.seek(0)

    filename = os.path.splitext(os.path.basename(image_field.name))[0] + '.jpg'
    image_field.save(filename, ContentFile(buf.read()), save=False)


# ── Asset helpers ─────────────────────────────────────────────────────────────

# Canonical MIME → friendly extension list. docx/xlsx/doc/xls are OOXML/OLE
# containers, so signature sniffing (libmagic) is the only reliable check.
ALLOWED_ASSET_MIME_TYPES = {
    'application/pdf': ['pdf'],
    'image/jpeg': ['jpg', 'jpeg'],
    'image/png': ['png'],
    'image/heic': ['heic'],
    'image/heif': ['heif'],
    'application/msword': ['doc'],
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['docx'],
    'application/vnd.ms-excel': ['xls'],
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['xlsx'],
    'video/mp4': ['mp4'],
}

# libmagic occasionally reports generic container types for OOXML/OLE files;
# map those back to the specific type using the filename extension.
_AMBIGUOUS_CONTAINER_MIMES = {
    'application/zip',
    'application/octet-stream',
    'application/x-ole-storage',
    'application/vnd.ms-office',
    'application/CDFV2',
}

_EXTENSION_TO_MIME = {
    'pdf': 'application/pdf',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'heic': 'image/heic',
    'heif': 'image/heif',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xls': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'mp4': 'video/mp4',
}

IMAGE_MIME_TYPES = {'image/jpeg', 'image/png', 'image/heic', 'image/heif'}
VIDEO_MIME_TYPES = {'video/mp4'}

# Ordered ascending — the upload dialog offers a prefix of this list (up to
# the source video's own height; never upscales). '2k'/'4k' follow the
# common consumer-tier naming (1440p/2160p), not the DCI cinema definitions.
VIDEO_RESOLUTION_CHOICES = {'480p': 480, '720p': 720, '1080p': 1080, '2k': 1440, '4k': 2160}


def probe_video_height(path):
    """Return a video file's pixel height via ffprobe, or None if it can't
    be determined (ffprobe missing, corrupt file, no video stream, ...)."""
    import json
    import subprocess

    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=height', '-of', 'json', path,
            ],
            check=True, capture_output=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    try:
        return int(json.loads(result.stdout)['streams'][0]['height'])
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError):
        return None


def download_field_to_temp(file_field, suffix):
    """Stream a FileField's content into a local temp file (ffmpeg needs a
    real path, not a storage-backed file-like object) and return its path.
    Caller owns cleanup (os.remove)."""
    import tempfile

    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, 'wb') as out:
        file_field.open('rb')
        try:
            for chunk in file_field.chunks():
                out.write(chunk)
        finally:
            file_field.close()
    return path


def extract_video_thumbnail(src_path):
    """Grab a representative JPEG frame (scaled to 320px wide) from a local
    video file via ffmpeg. Returns JPEG bytes, or None if no frame could be
    captured (ffmpeg missing, corrupt file, sub-1s clip, ...) — callers
    should treat that as "no thumbnail available", not a hard failure; the
    grid falls back to a plain MIME badge either way.
    """
    import subprocess
    import tempfile

    dst_fd, dst_path = tempfile.mkstemp(suffix='.jpg')
    os.close(dst_fd)
    try:
        # 1s in first (skips an all-black opening frame on most clips);
        # 0s as a fallback for anything shorter than that.
        for seek in ('00:00:01', '00:00:00'):
            try:
                subprocess.run(
                    [
                        'ffmpeg', '-y', '-ss', seek, '-i', src_path,
                        '-frames:v', '1', '-vf', 'scale=320:-2',
                        dst_path,
                    ],
                    check=True, capture_output=True, timeout=60,
                )
            except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                continue
            with open(dst_path, 'rb') as f:
                data = f.read()
            if data:
                return data
        return None
    finally:
        try:
            os.remove(dst_path)
        except OSError:
            pass


def transcode_video(src_path, resolution):
    """Run ffmpeg on a local video file, returning the compressed bytes for
    the given resolution tier (a key of VIDEO_RESOLUTION_CHOICES).

    Never upscales: the target height is capped to the source video's own
    height (via ffprobe) even if a higher tier was requested — the frontend
    dialog already hides tiers above the source resolution, but the source
    of truth has to be server-side since a client can send anything.

    Raises RuntimeError (ffmpeg missing / failed / timed out) — callers
    (ql.fee.tasks.asset_processing) are expected to catch it and mark the
    asset's processing_status FAILED rather than lose the original file.
    """
    import subprocess
    import tempfile

    target_height = VIDEO_RESOLUTION_CHOICES[resolution]
    source_height = probe_video_height(src_path)
    if source_height:
        target_height = min(target_height, source_height)

    dst_fd, dst_path = tempfile.mkstemp(suffix='.mp4')
    os.close(dst_fd)  # ffmpeg writes this path itself; just needed a free name
    try:
        try:
            subprocess.run(
                [
                    'ffmpeg', '-y', '-i', src_path,
                    '-vf', f'scale=-2:{target_height}',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '28',
                    '-c:a', 'aac', '-b:a', '128k',
                    '-movflags', '+faststart',
                    dst_path,
                ],
                check=True, capture_output=True, timeout=900,
            )
        except FileNotFoundError as exc:
            raise RuntimeError('ffmpeg is not installed on this server.') from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors='replace') if exc.stderr else ''
            raise RuntimeError(f'ffmpeg failed: {stderr[-500:]}') from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('ffmpeg timed out.') from exc

        with open(dst_path, 'rb') as f:
            return f.read()
    finally:
        try:
            os.remove(dst_path)
        except OSError:
            pass


def detect_asset_mime(fileobj, filename=''):
    """Sniff a file's MIME type from its signature bytes using libmagic.

    Falls back to the filename extension when libmagic returns a generic
    container type (common for docx/xlsx zip archives and legacy OLE docs).
    Returns the canonical MIME string (may be one not in the allow-list).
    """
    import magic

    pos = fileobj.tell() if hasattr(fileobj, 'tell') else None
    if hasattr(fileobj, 'seek'):
        fileobj.seek(0)
    head = fileobj.read(2048)
    if pos is not None:
        fileobj.seek(pos)

    detected = magic.from_buffer(head, mime=True) or 'application/octet-stream'

    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    if detected in _AMBIGUOUS_CONTAINER_MIMES and ext in _EXTENSION_TO_MIME:
        # Trust the extension only for the container formats we can't resolve
        # from magic bytes alone; the outer signature is already a valid
        # zip/OLE header, so this is a narrow, safe promotion.
        return _EXTENSION_TO_MIME[ext]
    return detected


def extract_image_metadata(fileobj):
    """Return a JSON-serialisable dict of image dimensions + EXIF, or {}."""
    from PIL import Image, ExifTags

    pos = fileobj.tell() if hasattr(fileobj, 'tell') else None
    try:
        if hasattr(fileobj, 'seek'):
            fileobj.seek(0)
        img = Image.open(fileobj)
        meta = {
            'width': img.width,
            'height': img.height,
            'format': img.format,
            'mode': img.mode,
        }
        exif = {}
        raw_exif = getattr(img, '_getexif', lambda: None)()
        if raw_exif:
            for tag_id, value in raw_exif.items():
                tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                # Keep only primitive, JSON-safe values.
                if isinstance(value, (str, int, float)):
                    exif[tag] = value
        if exif:
            meta['exif'] = exif
        return meta
    except Exception:
        return {}
    finally:
        if pos is not None and hasattr(fileobj, 'seek'):
            fileobj.seek(pos)
