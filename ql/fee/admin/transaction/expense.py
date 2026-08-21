from django import forms
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType

from ql.fee.models import ExpenseTransaction, Transaction, TransactionItem
from .base import BaseTransactionAdmin, FundGroupedSelect


class ExpenseTransactionItemForm(forms.ModelForm):
    class Meta:
        model   = TransactionItem
        fields  = ['fund', 'name', 'price', 'quantity', 'nominal']
        widgets = {'fund': FundGroupedSelect}

    class Media:
        js = ['ql/js/expense_item_nominal.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quantity'].required = False
        self.fields['nominal'].required = False
        self.fields['fund'].label = 'Source of fund'
        # Derived from price × quantity (see clean()); JS keeps it in sync live,
        # readonly (not disabled) so the browser still submits it for the
        # legacy-row fallback below.
        self.fields['nominal'].widget.attrs['readonly'] = 'readonly'

    def clean(self):
        cleaned_data = super().clean()
        fund     = cleaned_data.get('fund')
        price    = cleaned_data.get('price')
        quantity = cleaned_data.get('quantity')
        nominal  = cleaned_data.get('nominal')

        if not fund:
            return cleaned_data

        if quantity is None:
            quantity = 1
            cleaned_data['quantity'] = quantity

        if price is not None:
            cleaned_data['nominal'] = price * quantity
        elif nominal is None:
            self.add_error('price', 'Enter a price to calculate nominal.')

        return cleaned_data


class ExpenseTransactionItemInline(admin.TabularInline):
    model  = TransactionItem
    form   = ExpenseTransactionItemForm
    extra  = 0
    fields = ['fund', 'name', 'price', 'quantity', 'nominal']


@admin.register(ExpenseTransaction)
class ExpenseTransactionAdmin(BaseTransactionAdmin):
    _forced_direction    = Transaction.Direction.OUT
    inlines              = [ExpenseTransactionItemInline]
    list_display         = ['id', 'occurred_at', 'wallet_display', 'nominal_display', 'pic', 'status_icons', 'note_short', 'highlight_row', 'creator']
    change_form_template = 'admin/fee/expensetransaction/change_form.html'

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .filter(direction=self._forced_direction)
            .select_related('user', 'user__properties', 'wallet', 'receipt', 'creator', 'creator__properties')
        )

    @admin.display(description='PIC', ordering='user')
    def pic(self, obj):
        return obj.user

    @admin.display(description='From Wallet', ordering='wallet')
    def wallet_display(self, obj):
        return obj.wallet

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if form and 'user' in form.base_fields:
            form.base_fields['user'].label = 'PIC'
            form.base_fields['user'].help_text = 'Person In Charge — the resident responsible for this expense.'
        if form and 'wallet' in form.base_fields:
            form.base_fields['wallet'].label = 'From Wallet'
        return form

    def change_view(self, request, object_id, form_url='', extra_context=None):
        ct = ContentType.objects.get_for_model(Transaction)
        extra_context = {
            **(extra_context or {}),
            'asset_content_type_id': ct.id,
            'asset_object_id': object_id,
            'asset_purpose': 'expense_proof',
        }
        return super().change_view(request, object_id, form_url, extra_context)
