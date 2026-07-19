from django.contrib import admin
from django.utils.html import format_html

from ql.models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display    = ['id', 'original_name', 'mime_type', 'size_display', 'owner', 'purpose', 'created_at']
    list_filter     = ['mime_type', 'purpose', 'content_type', 'created_at']
    search_fields   = ['original_name', 'url']
    readonly_fields = ['content_type', 'object_id', 'mime_type', 'size', 'original_name', 'metadata', 'preview', 'created_at', 'updated_at', 'deleted_at']
    fields = [
        'content_type', 'object_id', 'purpose',
        'file', 'url',
        'original_name', 'mime_type', 'size', 'metadata', 'preview',
        'created_at', 'updated_at', 'deleted_at',
    ]

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
            fieldsets.append(('Audit', {'fields': ['created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}))
        return fieldsets

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
