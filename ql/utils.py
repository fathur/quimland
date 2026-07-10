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
