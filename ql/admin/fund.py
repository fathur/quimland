from django.contrib import admin

from ..models import CashEntry, Fund, FundDue
from ..utils import fmt_rupiah

class CashEntryInline(admin.TabularInline):
    model = CashEntry
    extra = 1
    autocomplete_fields = ['user']
    exclude = ['creator']


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

    def save_formset(self, request, _form, formset, change=False):
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk and hasattr(instance, 'creator_id') and not instance.creator_id:
                instance.creator = request.user
            instance.save()
        formset.save_m2m()

    @admin.display(description='Target Amount', ordering='target_amount')
    def target_amount_display(self, obj):
        if obj.target_amount is None:
            return '-'
        return fmt_rupiah(obj.target_amount)
