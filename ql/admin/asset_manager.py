"""AJAX endpoints + detail page powering the Asset grid manager.

Generic by design: every endpoint takes a (content_type_id, object_id) pair,
so the same widget can attach files to a Transaction today and to a User or
Property tomorrow — no per-model code required.
"""
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.views.decorators.http import require_POST

from ql.models import Asset

_MIME_LABEL = {
    'application/pdf': 'PDF',
    'application/msword': 'DOC',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
    'application/vnd.ms-excel': 'XLS',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX',
    'image/jpeg': 'JPG',
    'image/png': 'PNG',
}


def _human_size(n):
    if not n:
        return ''
    kb = n / 1024
    return f'{kb / 1024:.1f} MB' if kb > 1024 else f'{kb:.0f} KB'


def _asset_json(a):
    is_image = bool(a.mime_type.startswith('image/'))
    is_url = bool(a.url)
    return {
        'id': a.id,
        'name': a.original_name or a.url or f'Asset {a.id}',
        'mime': a.mime_type,
        'size_text': _human_size(a.size),
        'is_image': is_image,
        'is_url': is_url,
        'thumb_url': a.file.url if (is_image and a.file) else None,
        'label': 'URL' if is_url else _MIME_LABEL.get(a.mime_type, 'FILE'),
        # File assets open a detail page; URL assets open the target directly.
        'click_url': a.url if is_url else reverse('admin:asset_detail', args=[a.id]),
    }


def _resolve_owner(request):
    """Return (content_type, object_id) from the POST body, or raise ValueError."""
    ct_id = request.POST.get('content_type_id')
    obj_id = request.POST.get('object_id')
    if not ct_id or not obj_id:
        raise ValueError('Missing owner reference.')
    ct = get_object_or_404(ContentType, pk=ct_id)
    model = ct.model_class()
    if model is None or not model.objects.filter(pk=obj_id).exists():
        raise ValueError('Owner object not found.')
    return ct, obj_id


# ── Endpoints ─────────────────────────────────────────────────────────────────

@require_POST
def upload_view(request):
    try:
        ct, obj_id = _resolve_owner(request)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    purpose = request.POST.get('purpose', '') or ''
    created, errors = [], []
    for f in request.FILES.getlist('file'):
        asset = Asset(content_type=ct, object_id=obj_id, purpose=purpose, file=f)
        try:
            asset.full_clean()
            asset.save()
            created.append(_asset_json(asset))
        except ValidationError as exc:
            errors.append({'name': f.name, 'message': '; '.join(exc.messages)})

    return JsonResponse({'created': created, 'errors': errors})


@require_POST
def add_url_view(request):
    try:
        ct, obj_id = _resolve_owner(request)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    url = (request.POST.get('url') or '').strip()
    purpose = request.POST.get('purpose', '') or ''
    asset = Asset(content_type=ct, object_id=obj_id, purpose=purpose, url=url)
    try:
        asset.full_clean()
        asset.save()
    except ValidationError as exc:
        return JsonResponse({'error': '; '.join(exc.messages)}, status=400)
    return JsonResponse({'created': [_asset_json(asset)]})


@require_POST
def delete_view(request, asset_id):
    asset = get_object_or_404(Asset, pk=asset_id)
    if asset.file:
        asset.file.delete(save=False)
    asset.delete()
    return JsonResponse({'ok': True})


def list_view(request):
    ct_id = request.GET.get('content_type_id')
    obj_id = request.GET.get('object_id')
    qs = Asset.objects.filter(content_type_id=ct_id, object_id=obj_id).order_by('created_at')
    return JsonResponse({'assets': [_asset_json(a) for a in qs]})


def detail_view(request, asset_id):
    asset = get_object_or_404(Asset, pk=asset_id)
    meta_rows = sorted((asset.metadata or {}).items(), key=lambda kv: kv[0])
    context = {
        **admin.site.each_context(request),
        'title': asset.original_name or f'Asset #{asset.id}',
        'asset': asset,
        'is_image': asset.mime_type.startswith('image/'),
        'size_text': _human_size(asset.size),
        'label': _MIME_LABEL.get(asset.mime_type, 'FILE'),
        'meta_rows': meta_rows,
    }
    return render(request, 'admin/asset_detail.html', context)


# ── URL registration (chains onto the existing admin.get_urls) ────────────────
_original_get_urls = admin.site.get_urls


def _get_urls():
    custom = [
        path('asset-manager/upload/', admin.site.admin_view(upload_view), name='asset_upload'),
        path('asset-manager/add-url/', admin.site.admin_view(add_url_view), name='asset_add_url'),
        path('asset-manager/list/', admin.site.admin_view(list_view), name='asset_list'),
        path('asset-manager/<int:asset_id>/delete/', admin.site.admin_view(delete_view), name='asset_delete'),
        path('asset-manager/<int:asset_id>/', admin.site.admin_view(detail_view), name='asset_detail'),
    ]
    return custom + _original_get_urls()


admin.site.get_urls = _get_urls
