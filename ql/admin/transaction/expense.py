from django import forms
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType

from ql.models import ExpenseTransaction, Transaction, TransactionItem
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
    list_display         = ['id', 'occurred_at', 'wallet', 'nominal_display', 'pic', 'qris_icon', 'receipt_icon', 'note_short', 'highlight_row']
    change_form_template = 'admin/ql/expensetransaction/change_form.html'

    @admin.display(description='PIC', ordering='user')
    def pic(self, obj):
        return obj.user

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if form and 'user' in form.base_fields:
            form.base_fields['user'].label = 'PIC'
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
