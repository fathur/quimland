import mimetypes
import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseForbidden


def serve_secure_media(request, path):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    # Resolve and guard against path traversal before touching the filesystem.
    root = os.path.realpath(settings.SECURE_MEDIA_ROOT)
    target = os.path.realpath(os.path.join(root, path))
    if not target.startswith(root + os.sep):
        raise Http404

    if not os.path.isfile(target):
        raise Http404

    content_type, _ = mimetypes.guess_type(target)
    return FileResponse(
        open(target, 'rb'),  # noqa: WPS515 — FileResponse closes the file handle.
        content_type=content_type or 'application/octet-stream',
    )
