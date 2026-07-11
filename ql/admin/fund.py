from django import forms
from django.contrib import admin
from django.utils.html import format_html

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
    list_display = ['name', 'color_swatch', 'kind', 'status', 'target_amount_display', 'created_at']
    list_filter = ['kind', 'status']
    search_fields = ['name']
    # inlines = [CashEntryInline, FundDueInline]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'color':
            kwargs['widget'] = forms.TextInput(attrs={
                'type': 'color',
                'style': 'width:56px;height:36px;padding:2px;cursor:pointer;',
            })
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def save_formset(self, request, _form, formset, change=False):
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk and hasattr(instance, 'creator_id') and not instance.creator_id:
                instance.creator = request.user
            instance.save()
        formset.save_m2m()

    @admin.display(description='Color')
    def color_swatch(self, obj):
        color = obj.color or '#6b7280'
        return format_html(
            '<span style="display:inline-block;width:22px;height:22px;'
            'border-radius:4px;background:{};vertical-align:middle;'
            'border:1px solid rgba(0,0,0,.15);" title="{}"></span>',
            color, color,
        )

    @admin.display(description='Target Amount', ordering='target_amount')
    def target_amount_display(self, obj):
        if obj.target_amount is None:
            return '-'
        return fmt_rupiah(obj.target_amount)
