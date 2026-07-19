from django.contrib import admin

from ql.models import Loan
from ql.utils import fmt_rupiah


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display   = ['id', 'fund', 'kind', 'lender', 'principal_display', 'borrowed_at', 'status']
    list_filter    = ['kind', 'status', 'fund']
    search_fields  = ['fund__name', 'lender__username', 'lender__first_name', 'lender__last_name']
    ordering       = ['-borrowed_at']
    autocomplete_fields = ['fund', 'lender']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at']

    fieldsets = [
        (None, {'fields': ['fund', 'lender', 'kind', 'principal', 'borrowed_at', 'status', 'note']}),
        ('Audit', {'fields': ['created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}),
    ]

    @admin.display(description='Principal', ordering='principal')
    def principal_display(self, obj):
        return fmt_rupiah(obj.principal)
