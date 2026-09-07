from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from ql.fee.models import Transaction, WalletTransfer, WalletTransferReceipt
from ql.fee.services.utils import fmt_rupiah


@admin.register(WalletTransferReceipt)
class WalletTransferReceiptAdmin(admin.ModelAdmin):
    list_display    = ['id', 'user', 'storage', 'image_preview', 'created_at']
    list_filter     = ['storage']
    readonly_fields = ['storage', 'created_at', 'updated_at', 'image_preview']
    search_fields   = ['id', 'user__username', 'user__first_name', 'user__last_name']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    @admin.display(description='Preview')
    def image_preview(self, obj):
        if not obj or not obj.image:
            return '—'
        url = obj.image.url
        return format_html(
            '<a href="{}" target="_blank">'
            '<img src="{}" style="max-width:400px;max-height:400px;border-radius:8px;">'
            '</a>',
            url, url,
        )


class TransferLegInline(admin.TabularInline):
    model      = Transaction
    fk_name    = 'transfer'
    extra      = 0
    can_delete = False
    fields     = ['transaction_link', 'direction', 'wallet', 'nominal_display', 'occurred_at']
    readonly_fields = ['transaction_link', 'direction', 'wallet', 'nominal_display', 'occurred_at']
    verbose_name        = 'Transaction leg'
    verbose_name_plural = 'Transaction legs'

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='Transaction')
    def transaction_link(self, obj):
        if not obj.pk:
            return ''
        url = reverse('admin:fee_alltransaction_change', args=[obj.pk])
        return format_html('<a href="{}">#{}</a>', url, obj.pk)

    @admin.display(description='Nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)


class WalletTransferAdminForm(forms.ModelForm):
    receipt_image = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(),
        help_text='Upload a receipt image. Uploading a new file replaces the existing one.',
    )

    class Meta:
        model   = WalletTransfer
        exclude = ['receipt']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.receipt_id:
            try:
                self.fields['receipt_image'].initial = self.instance.receipt.image
            except WalletTransferReceipt.DoesNotExist:
                pass


@admin.register(WalletTransfer)
class WalletTransferAdmin(admin.ModelAdmin):
    form            = WalletTransferAdminForm
    list_display    = ['id', 'occurred_at', 'from_wallet', 'to_wallet', 'nominal_display', 'receipt_icon', 'note_short']
    list_filter     = ['from_wallet', 'to_wallet']
    search_fields   = ['from_wallet__name', 'to_wallet__name', 'note']
    ordering        = ['-occurred_at', '-created_at']
    readonly_fields = ['creator', 'created_at', 'updated_at', 'receipt_preview']
    inlines         = [TransferLegInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('receipt')

    def get_fieldsets(self, request, obj=None):
        receipt_fields = ['receipt_image']
        if obj and obj.receipt_id:
            receipt_fields.insert(0, 'receipt_preview')
        fieldsets = [
            (None, {'fields': ['occurred_at', 'from_wallet', 'to_wallet', 'nominal', 'note']}),
            ('Receipt', {'fields': receipt_fields}),
        ]
        if obj:
            fieldsets.append(('Audit', {'fields': ['creator', 'created_at', 'updated_at'], 'classes': ['collapse']}))
        return fieldsets

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creator = request.user
        super().save_model(request, obj, form, change)

        image = form.cleaned_data.get('receipt_image')
        if image is False:
            if obj.receipt_id:
                old = obj.receipt
                obj.receipt = None
                obj.save(update_fields=['receipt'])
                old.delete()
        elif image:
            if obj.receipt_id:
                receipt = obj.receipt
                receipt.image = image
                receipt.user_id = obj.creator_id
                receipt.save()
            else:
                receipt = WalletTransferReceipt(user_id=obj.creator_id, image=image)
                receipt.save()
                obj.receipt = receipt
                obj.save(update_fields=['receipt'])

    def delete_queryset(self, request, queryset):
        # See BaseTransactionAdmin.delete_queryset — bulk queryset.delete()
        # would skip WalletTransfer.delete()'s cascade to both legs.
        for obj in queryset:
            obj.delete()

    @admin.display(description='Nominal', ordering='nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)

    @admin.display(description='', ordering='receipt')
    def receipt_icon(self, obj):
        if not obj.receipt_id or not obj.receipt.image:
            return ''
        url = reverse('admin:fee_wallettransferreceipt_change', args=[obj.receipt_id])
        return format_html(
            '<a href="{}" title="View receipt">🧾</a>', url,
        )

    @admin.display(description='Receipt preview')
    def receipt_preview(self, obj):
        if not obj or not obj.receipt_id or not obj.receipt.image:
            return '—'
        return format_html(
            '<a href="{}" target="_blank">'
            '<img src="{}" style="max-width:400px;max-height:400px;border-radius:8px;">'
            '</a>',
            obj.receipt.image.url, obj.receipt.image.url,
        )

    @admin.display(description='Note')
    def note_short(self, obj):
        return (obj.note[:60] + '…') if len(obj.note) > 60 else obj.note
