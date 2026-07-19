from django.contrib import admin
from django.utils.html import format_html

from ql.models import Transaction, WalletTransfer
from ql.utils import fmt_rupiah


class TransferLegInline(admin.TabularInline):
    model      = Transaction
    fk_name    = 'transfer'
    extra      = 0
    can_delete = False
    fields     = ['direction', 'wallet', 'nominal_display', 'occurred_at']
    readonly_fields = ['direction', 'wallet', 'nominal_display', 'occurred_at']
    verbose_name        = 'Transaction leg'
    verbose_name_plural = 'Transaction legs'

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='Nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)


@admin.register(WalletTransfer)
class WalletTransferAdmin(admin.ModelAdmin):
    list_display    = ['id', 'occurred_at', 'from_wallet', 'to_wallet', 'nominal_display', 'note_short']
    list_filter     = ['from_wallet', 'to_wallet']
    search_fields   = ['from_wallet__name', 'to_wallet__name', 'note']
    ordering        = ['-occurred_at', '-created_at']
    readonly_fields = ['creator', 'created_at', 'updated_at']
    inlines         = [TransferLegInline]

    def get_fields(self, request, obj=None):
        fields = ['from_wallet', 'to_wallet', 'nominal', 'occurred_at', 'note']
        if obj:
            fields += ['creator', 'created_at', 'updated_at']
        return fields
    
    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {'fields': [ 'occurred_at', 'from_wallet', 'to_wallet', 'nominal', 'note']}),
        ]
        if obj:
            fieldsets.append(('Audit', {'fields': ['creator', 'created_at', 'updated_at'], 'classes': ['collapse']}))
        return fieldsets

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creator = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description='Nominal', ordering='nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)

    @admin.display(description='Note')
    def note_short(self, obj):
        return (obj.note[:60] + '…') if len(obj.note) > 60 else obj.note
