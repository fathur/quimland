from django.contrib import admin
from django.utils.html import format_html, format_html_join

from ..models import Loan, Project
from ..utils import fmt_rupiah


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display    = ['id', 'fund', 'pic', 'pic_fee_display', 'created_at']
    search_fields   = ['fund__name', 'pic__username', 'pic__first_name', 'pic__last_name']
    autocomplete_fields = ['fund', 'pic']
    readonly_fields = ['loans_summary', 'created_at', 'updated_at']

    fieldsets = [
        (None, {'fields': ['fund', 'pic', 'pic_fee']}),
        ('Loans', {'fields': ['loans_summary']}),
        ('Audit', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    @admin.display(description='PIC Fee', ordering='pic_fee')
    def pic_fee_display(self, obj):
        return fmt_rupiah(obj.pic_fee)

    @admin.display(description='Fund loans')
    def loans_summary(self, obj):
        if not obj or not obj.pk:
            return '—'
        loans = Loan.objects.filter(fund=obj.fund).order_by('kind', '-borrowed_at')
        if not loans.exists():
            return 'No loans.'
        rows = format_html_join(
            '',
            '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>',
            (
                (l.get_kind_display(), l.lender or '—',
                 fmt_rupiah(l.principal), l.borrowed_at, l.get_status_display())
                for l in loans
            ),
        )
        return format_html(
            '<table style="width:100%">'
            '<thead><tr><th>Kind</th><th>Lender</th><th>Principal</th>'
            '<th>Date</th><th>Status</th></tr></thead>'
            '<tbody>{}</tbody></table>',
            rows,
        )
