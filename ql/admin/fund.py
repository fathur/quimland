from django import forms
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from mptt.admin import MPTTModelAdmin

from ql.models import CashEntry, Fund, FundDue
from ql.reports import generate_fund_report_draft
from ql.utils import fmt_rupiah


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
class FundAdmin(MPTTModelAdmin):
    list_display = ['name', 'color_swatch', 'kind', 'parent', 'status', 'target_amount_display']
    list_filter = ['kind', 'status']
    search_fields = ['name']
    actions = ['generate_report_action']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at']
    # inlines = [CashEntryInline, FundDueInline]

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {'fields': ['parent', 'name', 'color', 'kind', 'description', 'target_amount', 'status']}),
        ]
        if obj:
            fieldsets.append(('Audit', {'fields': ['created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}))
        return fieldsets

    def get_urls(self):
        return [
            path(
                '<int:fund_id>/generate-report/',
                self.admin_site.admin_view(self.generate_report_view),
                name='ql_fund_generate_report',
            ),
        ] + super().get_urls()

    def generate_report_view(self, request, fund_id):
        fund = get_object_or_404(Fund, pk=fund_id)
        if not self.has_view_permission(request, fund):
            self.message_user(request, 'You do not have permission to generate reports.', level=messages.ERROR)
            return redirect('admin:ql_fund_changelist')
        if fund.status != Fund.Status.CLOSED:
            self.message_user(request, f'"{fund.name}" belum ditutup. Laporan hanya dapat dibuat untuk dana yang sudah ditutup.', level=messages.ERROR)
            return redirect('admin:ql_fund_changelist')
        report = generate_fund_report_draft(fund, request.user)
        self.message_user(request, f'Draf laporan untuk "{fund.name}" berhasil dibuat. Silakan tinjau dan sunting kontennya.')
        return redirect('admin:ql_report_change', report.pk)

    @admin.action(description='Generate report draft (closed funds only)')
    def generate_report_action(self, request, queryset):
        if not self.has_view_permission(request):
            self.message_user(request, 'You do not have permission to generate reports.', level=messages.ERROR)
            return
        generated, skipped = 0, 0
        for fund in queryset:
            if fund.status != Fund.Status.CLOSED:
                skipped += 1
                continue
            generate_fund_report_draft(fund, request.user)
            generated += 1
        if generated:
            self.message_user(request, f'{generated} draf laporan berhasil dibuat.')
        if skipped:
            self.message_user(request, f'{skipped} dana dilewati karena belum ditutup.', level=messages.WARNING)

    @admin.display(description='Report')
    def generate_report_link(self, obj):
        if obj.status != Fund.Status.CLOSED:
            return mark_safe('<span style="color:var(--body-quiet-color);font-size:11px;">—</span>')
        url = reverse('admin:ql_fund_generate_report', args=[obj.pk])
        return format_html('<a class="button" href="{}">Generate report draft</a>', url)

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
