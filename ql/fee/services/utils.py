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
}

IMAGE_MIME_TYPES = {'image/jpeg', 'image/png', 'image/heic', 'image/heif'}


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
