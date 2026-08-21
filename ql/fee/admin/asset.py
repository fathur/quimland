from django.contrib import admin
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html, mark_safe

from ql.fee.models import Asset
from .mixins import LazyMediaGridAdmin


@admin.register(Asset)
class AssetAdmin(LazyMediaGridAdmin, admin.ModelAdmin):
    list_display    = ['id', 'original_name', 'mime_type', 'size_display', 'owner', 'purpose', 'created_at']
    list_filter     = ['mime_type', 'purpose', 'content_type', 'created_at']
    list_per_page   = 12
    search_fields   = ['original_name', 'url']
    readonly_fields = ['content_type', 'object_id', 'mime_type', 'size', 'original_name', 'metadata', 'preview', 'related_records', 'created_at', 'updated_at', 'deleted_at']

    # GenericForeignKey targets resolve to their *concrete* model's
    # ContentType (fee.transaction), but that base model has no admin of its
    # own registered — only its proxies do (IncomeTransactionAdmin etc.).
    # AllTransactionAdmin is the read-only "view any transaction" one, so
    # that's what a Transaction-owned asset should link to. Extend this if
    # another owner model ever ends up in the same situation.
    _content_type_admin_overrides = {
        'transaction': 'alltransaction',
    }
    fields = [
        'content_type', 'object_id', 'purpose',
        'file', 'url',
        'original_name', 'mime_type', 'size', 'metadata', 'preview',
        'related_records',
        'created_at', 'updated_at', 'deleted_at',
    ]

    grid_fragment_template = 'admin/fee/asset/_grid_items.html'

    class Media:
        css = {'all': ['admin/css/media_grid.css']}
        js = ['admin/js/media_grid.js']

    def get_queryset(self, request):
        # owner() reads obj.content_object (a GenericForeignKey) for every row —
        # without prefetching, that's one query per row (N+1). prefetch_related
        # batches it per distinct content type instead.
        return super().get_queryset(request).select_related('content_type').prefetch_related('content_object')

    def get_grid_image_url(self, obj):
        # Only actual images pay the (possibly expensive, e.g. R2-signed)
        # URL cost — PDFs/docs and external links render a static
        # placeholder in the fragment template instead, no AJAX needed.
        if obj.file and 'image/' in obj.mime_type:
            return obj.file.url
        return None

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {'fields': [
                'content_type', 'object_id', 'purpose',
                'file', 'url',
                'original_name', 'mime_type', 'size', 'metadata', 'preview',
                # 'created_at', 'updated_at',
            ]}),
        ]
        if obj:
            fieldsets.append(('Used by', {'fields': ['related_records']}))
            fieldsets.append(('Audit', {'fields': ['created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}))
        return fieldsets

    @admin.display(description='Related records')
    def related_records(self, obj):
        if not obj or not obj.pk:
            return '—'
        content_object = obj.content_object
        if content_object is None:
            return mark_safe('<span style="color:var(--body-quiet-color);">Not attached to any record.</span>')

        ct = obj.content_type
        model_name = self._content_type_admin_overrides.get(ct.model, ct.model)
        try:
            url = reverse(f'admin:{ct.app_label}_{model_name}_change', args=[obj.object_id])
        except NoReverseMatch:
            return str(content_object)

        return format_html('<a href="{}">{}: {}</a>', url, ct.name.capitalize(), content_object)

    @admin.display(description='Size')
    def size_display(self, obj):
        if not obj.size:
            return '—'
        kb = obj.size / 1024
        return f'{kb / 1024:.1f} MiB' if kb > 1024 else f'{kb:.0f} KiB'

    @admin.display(description='Attached to')
    def owner(self, obj):
        return obj.content_object or '—'

    @admin.display(description='Preview')
    def preview(self, obj):
        if obj.url:
            return format_html('<a href="{}" target="_blank">{}</a>', obj.url, obj.url)
        if obj.file and obj.mime_type.startswith('image/'):
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-height:300px;border-radius:8px;"></a>',
                obj.file.url, obj.file.url,
            )
        if obj.file:
            return format_html('<a href="{}" target="_blank">download</a>', obj.file.url)
        return '—'
