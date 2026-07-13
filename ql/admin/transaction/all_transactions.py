from decimal import Decimal

from django.contrib import admin
from django.db.models import Q, Sum

from ql.models import AllTransaction, Transaction
from ql.utils import fmt_rupiah
from .base import OccurredAtRangeFilter


class AllTransactionAdmin(admin.ModelAdmin):
    list_display        = ['id', 'occurred_at', 'direction', 'wallet', 'user', 'nominal_display', 'note_short']
    list_filter         = [OccurredAtRangeFilter, 'wallet', 'user']
    search_fields       = ['user__username', 'user__first_name', 'user__last_name', 'note']
    ordering            = ['-occurred_at', '-created_at']
    readonly_fields     = ['direction', 'nominal', 'occurred_at', 'user', 'wallet', 'note',
                           'creator', 'created_at', 'updated_at']

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .filter(direction__in=[Transaction.Direction.IN, Transaction.Direction.OUT])
            # .filter(transfer__isnull=True)
        )

    def has_add_permission(self, request):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def has_delete_permission(self, request, obj=None):  # noqa: ARG002
        return False

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
        except (AttributeError, KeyError):
            pass
        return response

    @admin.display(description='Nominal', ordering='nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)

    @admin.display(description='Note')
    def note_short(self, obj):
        return (obj.note[:60] + '…') if len(obj.note) > 60 else obj.note


admin.site.register(AllTransaction, AllTransactionAdmin)
