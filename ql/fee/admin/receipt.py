from django.contrib import admin
from django.contrib.admin.options import IncorrectLookupParameters
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import path
from django.utils.html import format_html

from ql.fee.models import Receipt


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display  = ['id', 'user', 'storage', 'image_preview', 'created_at']
    list_filter   = ['storage']
    list_per_page = 12
    readonly_fields = ['storage', 'user', 'created_at', 'updated_at', 'deleted_at', 'image_preview']
    search_fields = ['id', 'user__username', 'user__first_name', 'user__last_name']

    class Media:
        css = {'all': ['admin/css/receipt_grid.css']}
        js = ['admin/js/receipt_grid.js']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'user__properties')

    def get_fields(self, request, obj=None):
        if obj:
            return ['user', 'image', 'image_preview', 'storage', 'created_at', 'updated_at', 'deleted_at']
        return ['user', 'image']

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {'fields': ['user', 'image', 'image_preview', 'storage']}),
        ]
        if obj:
            fieldsets.append(('Audit', {'fields': ['created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}))
        return fieldsets

    @admin.display(description='Preview')
    def image_preview(self, obj):
        if not obj or not obj.image:
            return '—'
        url = obj.image.url
        return format_html(
            '<a href="{}" target="_blank">'
            '<img src="{}" style="max-width:400px;max-height:400px;border-radius:8px;">'
            '</a>',
            url, url,
        )

    def save_model(self, request, obj, form, change):
        if not change and not obj.user_id:
            obj.user_id = request.user.pk
        super().save_model(request, obj, form, change)

    # ── Grid changelist: lazy image loading ────────────────────────────────
    # obj.image.url is expensive for R2-backed receipts (~100ms — boto3
    # bootstraps a client and signs the URL on first real use). Rendering it
    # inline for every row on the changelist multiplies that cost by the page
    # size. These two endpoints move that cost off the page-render path: the
    # grid renders placeholders first, then JS fetches each box's real image
    # URL (and the next batch, for "Load more") asynchronously.
    def get_urls(self):
        return [
            path(
                '<int:receipt_id>/url-image/',
                self.admin_site.admin_view(self.url_image_view),
                name='fee_receipt_url_image',
            ),
            path(
                'load-more/',
                self.admin_site.admin_view(self.load_more_view),
                name='fee_receipt_load_more',
            ),
        ] + super().get_urls()

    def url_image_view(self, request, receipt_id):
        if not self.has_view_permission(request):
            return JsonResponse({'error': 'forbidden'}, status=403)
        obj = get_object_or_404(self.get_queryset(request), pk=receipt_id)
        if not obj.image:
            raise Http404('Receipt has no image.')
        return JsonResponse({'url': obj.image.url})

    def load_more_view(self, request):
        if not self.has_view_permission(request):
            return JsonResponse({'error': 'forbidden'}, status=403)
        try:
            cl = self.get_changelist_instance(request)
        except IncorrectLookupParameters:
            # e.g. a page number past the end — stale tab, tampered URL.
            return JsonResponse({'html': '', 'has_more': False})
        html = render_to_string(
            'admin/fee/receipt/_grid_items.html',
            {'object_list': cl.result_list},
            request=request,
        )
        has_more = cl.page_num < cl.paginator.num_pages
        return JsonResponse({'html': html, 'has_more': has_more})
