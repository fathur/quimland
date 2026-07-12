from django.contrib import admin
from django.utils.html import format_html

from ql.models import PropertyTax


@admin.register(PropertyTax)
class PropertyTaxAdmin(admin.ModelAdmin):
    list_display = ['user', 'nop', 'land_area_display', 'building_area_display', 'attachment_icon']
    search_fields = ['user__first_name', 'user__last_name', 'user__username', 'nop']
    autocomplete_fields = ['user']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user__properties')

    @admin.display(description='Land Area (m²)', ordering='land_area')
    def land_area_display(self, obj):
        return f'{obj.land_area:,} m²'

    @admin.display(description='Building Area (m²)', ordering='building_area')
    def building_area_display(self, obj):
        return f'{obj.building_area:,} m²'

    @admin.display(description='', ordering='attachment')
    def attachment_icon(self, obj):
        if not obj.attachment:
            return '—'
        return format_html(
            '<a href="{}" target="_blank" title="View attachment">'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
            ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
            ' stroke-linejoin="round" width="16" height="16"'
            ' style="vertical-align:middle;color:var(--body-fg)">'
            '<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19'
            ' a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>'
            '</svg>'
            '</a>',
            obj.attachment.url,
        )
