from django.contrib import admin

from ..models import CashEntry, Fund, FundDue
from ..utils import fmt_rupiah

class CashEntryInline(admin.TabularInline):
    model = CashEntry
    extra = 1
    autocomplete_fields = ['user', 'creator']


class FundDueInline(admin.TabularInline):
    model = FundDue
    extra = 1
    autocomplete_fields = ['user']


@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = ['name', 'kind', 'status', 'target_amount_display', 'created_at']
    list_filter = ['kind', 'status']
    search_fields = ['name']
    inlines = [CashEntryInline, FundDueInline]

    @admin.display(description='Target Amount', ordering='target_amount')
    def target_amount_display(self, obj):
        if obj.target_amount is None:
            return '-'
        return fmt_rupiah(obj.target_amount)
