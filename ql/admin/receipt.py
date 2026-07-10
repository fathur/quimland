from django.contrib import admin
from django.utils.html import format_html

from ..models import Receipt


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display  = ['id', 'user', 'receipt_storage', 'image_preview', 'created_at']
    list_filter   = ['receipt_storage']
    readonly_fields = ['receipt_storage', 'user', 'created_at', 'updated_at', 'image_preview']
    search_fields = ['id']

    def get_fields(self, request, obj=None):
        if obj:
            return ['user', 'image', 'image_preview', 'receipt_storage', 'created_at', 'updated_at']
        return ['user', 'image']

    @admin.display(description='Preview')
    def image_preview(self, obj):
        if not obj or not obj.image:
            return '—'
        return format_html(
            '<a href="{}" target="_blank">'
            '<img src="{}" style="max-width:400px;max-height:400px;border-radius:8px;">'
            '</a>',
            obj.image.url, obj.image.url,
        )

    def save_model(self, request, obj, form, change):
        if not change and not obj.user_id:
            obj.user_id = request.user.pk
        super().save_model(request, obj, form, change)
