from django.contrib import admin

from ql.models import WalletTransfer
from ql.utils import fmt_rupiah


@admin.register(WalletTransfer)
class WalletTransferAdmin(admin.ModelAdmin):
    list_display   = ['id', 'from_wallet', 'to_wallet', 'nominal_display', 'occurred_at', 'note_short']
    list_filter    = ['from_wallet', 'to_wallet']
    search_fields  = ['from_wallet__name', 'to_wallet__name', 'note']
    ordering       = ['-occurred_at', '-created_at']
    readonly_fields = ['creator', 'created_at', 'updated_at']
    fields         = ['from_wallet', 'to_wallet', 'nominal', 'occurred_at', 'note']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creator = request.user
        super().save_model(request, obj, form, change)

    def get_fields(self, request, obj=None):
        fields = ['from_wallet', 'to_wallet', 'nominal', 'occurred_at', 'note']
        if obj:
            fields += ['creator', 'created_at', 'updated_at']
        return fields

    @admin.display(description='Nominal', ordering='nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)

    @admin.display(description='Note')
    def note_short(self, obj):
        return (obj.note[:60] + '…') if len(obj.note) > 60 else obj.note
