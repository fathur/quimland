from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from ql.models import Transaction, TransactionItem
from ql.utils import fmt_rupiah
from .filters import SoftDeleteAdminMixin, SoftDeleteFilter


@admin.register(TransactionItem)
class TransactionItemAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    """View-only listing — items are created/edited through a Transaction's
    inline formset, which also keeps ItemRoutine and nominal-mismatch checks
    in sync. Editing here directly would bypass that."""

    list_display         = ['id', 'transaction_link', 'transaction__user', 'occurred_at', 'fund', 'name', 'direction_display', 'price_display', 'quantity', 'nominal_display', 'receipt_icon']
    list_filter          = [SoftDeleteFilter, 'fund', 'direction']
    search_fields        = ['id', 'name', 'transaction__id', 'transaction__note']
    ordering             = ['-created_at']
    list_select_related  = ['transaction__user', 'transaction__receipt', 'fund']

    def has_add_permission(self, request):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def has_delete_permission(self, request, obj=None):  # noqa: ARG002
        return False

    @admin.display(description='Transaction')
    def transaction_link(self, obj):
        url = reverse('admin:ql_alltransaction_change', args=[obj.transaction_id])
        return format_html('<a href="{}">#{}</a>', url, obj.transaction_id)

    @admin.display(description='Occurred at', ordering='transaction__occurred_at')
    def occurred_at(self, obj):
        # transaction is select_related (list_select_related above), so this
        # doesn't add a query per row.
        return obj.transaction.occurred_at

    @admin.display(description='Direction')
    def direction_display(self, obj):
        return Transaction.Direction(obj.effective_direction()).label

    @admin.display(description='Nominal', ordering='nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)

    @admin.display(description='Price', ordering='price')
    def price_display(self, obj):
        if obj.price is None:
            return '-'
        return fmt_rupiah(obj.price)

    @admin.display(description='', ordering='transaction__receipt')
    def receipt_icon(self, obj):
        # transaction__receipt is select_related (list_select_related above),
        # so this doesn't add a query per row.
        if not obj.transaction.receipt or not obj.transaction.receipt.image:
            return '—'
        return format_html(
            '<a href="{}" target="_blank" title="View receipt">'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
            ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
            ' stroke-linejoin="round" width="16" height="16"'
            ' style="vertical-align:middle;color:var(--body-fg)">'
            '<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19'
            ' a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>'
            '</svg>'
            '</a>',
            obj.transaction.receipt.image.url,
        )

 