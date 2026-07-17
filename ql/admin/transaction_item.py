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

    list_display         = ['id', 'transaction_link', 'occurred_at', 'fund', 'name', 'direction_display', 'price_display', 'quantity', 'nominal_display']
    list_filter          = [SoftDeleteFilter, 'fund', 'direction']
    search_fields        = ['id', 'name', 'transaction__id', 'transaction__note']
    ordering             = ['-created_at']
    list_select_related  = ['transaction', 'fund']

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

 