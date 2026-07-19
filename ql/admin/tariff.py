from django.contrib import admin

from ql.models import Tariff


@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ['user', 'fund', 'nominal', 'start_from', 'end_to']
    list_filter = ['fund']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    ordering = ['user', 'fund', 'start_from']
    autocomplete_fields = ['user']
    exclude = ['kind']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at']

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {'fields': ['user', 'fund', 'nominal', 'start_from', 'end_to']}),
        ]
        if obj:
            fieldsets.append(('Audit', {'fields': ['created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}))
        return fieldsets
