from django.contrib import admin
from django.utils.html import format_html

from ql.models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'fund', 'status', 'creator', 'created_at', 'completed_at', 'file_link']
    list_filter = ['status', 'fund']
    search_fields = ['title', 'fund__name']
    readonly_fields = ['title', 'fund', 'file', 'creator', 'status', 'completed_at', 'created_at', 'updated_at']

    def has_add_permission(self, request):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False

    @admin.display(description='File')
    def file_link(self, obj):
        if not obj.file:
            return '—'
        return format_html('<a href="{}" target="_blank">View PDF</a>', obj.file.url)
