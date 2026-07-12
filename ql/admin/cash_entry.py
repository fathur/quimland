from django.contrib import admin

from ql.models import CashEntry


@admin.register(CashEntry)
class CashEntryAdmin(admin.ModelAdmin):
    list_display = ['fund', 'direction', 'amount', 'occurred_at', 'user', 'category', 'creator']
    list_filter = ['fund', 'direction', 'category']
    search_fields = ['user__username', 'category', 'description']
    ordering = ['-occurred_at']
    autocomplete_fields = ['fund', 'user']

    


    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user__properties', 'creator__properties',
        )

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if not obj:
            return [f for f in fields if f != 'creator']
        return fields

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ['creator']
        return []

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creator = request.user
        super().save_model(request, obj, form, change)
