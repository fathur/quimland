from decimal import Decimal

from django.contrib import admin
from django.db.models import F, Q, Sum
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html, mark_safe

from django.contrib.contenttypes.models import ContentType

from ql.models import AllTransaction, Transaction, TransactionItem
from ql.utils import fmt_rupiah
from .base import OccurredAtRangeFilter
from ..filters import SoftDeleteAdminMixin, SoftDeleteFilter


class TransactionItemInline(admin.TabularInline):
    model           = TransactionItem
    extra           = 0
    fields          = ['fund', 'name', 'price', 'quantity', 'nominal']
    readonly_fields = fields
    can_delete      = False

    def has_add_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def has_delete_permission(self, request, obj=None):  # noqa: ARG002
        return False


class AllTransactionAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display        = ['id', 'occurred_at', 'direction', 'wallet', 'user', 'nominal_display', 'qris_icon', 'note_short', 'highlight_row']
    list_filter         = [SoftDeleteFilter, OccurredAtRangeFilter, 'wallet', 'user']
    search_fields       = ['user__username', 'user__first_name', 'user__last_name', 'note']
    ordering            = ['-occurred_at', '-created_at']
    readonly_fields     = ['direction', 'nominal', 'occurred_at', 'user', 'wallet', 'note',
                           'highlight', 'creator', 'created_at', 'updated_at', 'deleted_at']
    inlines             = [TransactionItemInline]

    def get_fieldsets(self, request, obj=None):
        return [
            (None, {'fields': ['direction', 'nominal', 'occurred_at', 'user', 'wallet', 'note']}),
            ('Audit', {'fields': ['highlight', 'creator', 'created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}),
        ]

    class Media:
        css = {'all': ['admin/css/transaction_highlight.css']}

    def get_urls(self):
        return [
            path('export-pdf/', self.admin_site.admin_view(self.export_pdf_view), name='ql_alltransaction_export_pdf'),
        ] + super().get_urls()

    def export_pdf_view(self, request):
        import weasyprint

        cl  = self.get_changelist_instance(request)
        qs  = cl.get_queryset(request).select_related('user', 'user__properties', 'wallet')

        agg = qs.aggregate(
            income=Sum('nominal', filter=Q(direction=Transaction.Direction.IN)),
            expense=Sum('nominal', filter=Q(direction=Transaction.Direction.OUT)),
        )
        income  = agg['income']  or Decimal('0')
        expense = agg['expense'] or Decimal('0')
        balance = income - expense

        html = render_to_string('admin/ql/alltransaction/export_pdf.html', {
            'transactions':    qs,
            'income_total':    fmt_rupiah(income),
            'expense_total':   fmt_rupiah(expense),
            'balance_total':   fmt_rupiah(balance),
            'balance_negative': balance < 0,
            'exported_at':     timezone.localtime(timezone.now()),
            'exported_by':     request.user,
            'count':           qs.count(),
        })

        pdf = weasyprint.HTML(string=html).write_pdf()
        filename = f"transactions-{timezone.localdate()}.pdf"
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def get_queryset(self, request):
        # super() → SoftDeleteAdminMixin.get_queryset → with_deleted() base
        return (
            super().get_queryset(request)
            .filter(direction__in=[Transaction.Direction.IN, Transaction.Direction.OUT])
        )

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.get_object(request, object_id)
        ct  = ContentType.objects.get_for_model(Transaction)
        extra_context = {
            **(extra_context or {}),
            'asset_content_type_id': ct.id,
            'asset_object_id':       object_id,
            'receipt_url': obj.receipt.image.url if obj and obj.receipt and obj.receipt.image else None,
        }
        return super().change_view(request, object_id, form_url, extra_context)

    def has_add_permission(self, request):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def has_delete_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def _imbalance_data(self):
        mismatched = list(
            Transaction.objects
            .filter(transfer__isnull=True)
            .annotate(total_items=Sum('items__nominal'))
            .filter(~Q(nominal=F('total_items')) | Q(total_items__isnull=True))
            .select_related('wallet', 'user')
            .order_by('-occurred_at')
        )
        contaminated = list(
            Transaction.objects
            .filter(transfer__isnull=False)
            .annotate(total_items=Sum('items__nominal'))
            .filter(total_items__isnull=False)
            .select_related('wallet', 'user')
            .order_by('-occurred_at')
        )
        return {
            'imbalance_mismatched':           mismatched,
            'imbalance_mismatched_count':     len(mismatched),
            'imbalance_contaminated':         contaminated,
            'imbalance_contaminated_count':   len(contaminated),
        }

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data['cl'].queryset
            agg = qs.aggregate(
                income=Sum('nominal', filter=Q(direction=Transaction.Direction.IN)),
                expense=Sum('nominal', filter=Q(direction=Transaction.Direction.OUT)),
            )
            income  = agg['income']  or Decimal('0')
            expense = agg['expense'] or Decimal('0')
            balance = income - expense
            response.context_data['income_total']  = fmt_rupiah(income)
            response.context_data['expense_total'] = fmt_rupiah(expense)
            response.context_data['balance_total'] = fmt_rupiah(balance)
            response.context_data['balance_negative'] = balance < 0
            response.context_data['nominal_total_count'] = qs.count()
            response.context_data.update(self._imbalance_data())
        except (AttributeError, KeyError):
            pass
        return response

    @admin.display(description='QRIS', ordering='is_qris')
    def qris_icon(self, obj):
        if not obj.is_qris:
            return ''
        return mark_safe(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
            ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
            ' stroke-linejoin="round" width="16" height="16"'
            ' title="QRIS" style="vertical-align:middle;color:var(--body-fg)">'
            '<rect x="3" y="3" width="7" height="7" rx="1"/>'
            '<rect x="14" y="3" width="7" height="7" rx="1"/>'
            '<rect x="3" y="14" width="7" height="7" rx="1"/>'
            '<rect x="5" y="5" width="3" height="3" fill="currentColor" stroke="none"/>'
            '<rect x="16" y="5" width="3" height="3" fill="currentColor" stroke="none"/>'
            '<rect x="5" y="16" width="3" height="3" fill="currentColor" stroke="none"/>'
            '<path d="M14 14h3v3h-3zM17 17h3v3h-3zM14 20h3"/>'
            '</svg>'
        )

    @admin.display(description='')
    def highlight_row(self, obj):
        if obj.highlight:
            return format_html('<span class="row-hl row-hl--{}" hidden></span>', obj.highlight)
        return ''

    @admin.display(description='Nominal', ordering='nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)

    @admin.display(description='Note')
    def note_short(self, obj):
        return (obj.note[:60] + '…') if len(obj.note) > 60 else obj.note


admin.site.register(AllTransaction, AllTransactionAdmin)
