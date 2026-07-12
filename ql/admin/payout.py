from django.contrib import admin

from ql.models import Payout


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ['payee', 'period', 'payout_date', 'amount', 'creator', 'note']
    list_filter = ['payee', 'period']
    search_fields = ['payee', 'period']
    ordering = ['payout_date', 'payee']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('creator__properties')

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
