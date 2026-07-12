from django.contrib import admin

from ql.models import FundDue
from ql.utils import fmt_rupiah


@admin.register(FundDue)
class FundDueAdmin(admin.ModelAdmin):
    list_display = ['fund', 'user', 'home_number', 'expected_amount_display']
    list_filter = ['fund']
    search_fields = ['user__username', 'user__first_name', 'fund__name']
    autocomplete_fields = ['fund', 'user']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user__properties')

    @admin.display(description='Home No.', ordering='user__properties__home_number')
    def home_number(self, obj):
        prop = getattr(obj.user, 'properties', None)
        return (prop.home_number if prop else None) or '—'

    @admin.display(description='Expected Amount', ordering='expected_amount')
    def expected_amount_display(self, obj):
        return fmt_rupiah(obj.expected_amount)
