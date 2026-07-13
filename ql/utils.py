import io
import os

from django.core.files.base import ContentFile


def fmt_rupiah(amount):
    formatted = f'{amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'Rp {formatted}'


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
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xls': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}

IMAGE_MIME_TYPES = {'image/jpeg', 'image/png'}


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
