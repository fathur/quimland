from django import forms
from django.contrib import admin

from ql.models import Transaction, TransactionItem, TransferTransaction
from .base import BaseTransactionAdmin, FundGroupedSelect


class TransferTransactionItemForm(forms.ModelForm):
    class Meta:
        model   = TransactionItem
        fields  = ['fund', 'direction', 'nominal']
        widgets = {'fund': FundGroupedSelect}

    def clean(self):
        cleaned_data = super().clean()
        fund      = cleaned_data.get('fund')
        direction = cleaned_data.get('direction')

        if not fund:
            return cleaned_data

        if not direction:
            self.add_error('direction', 'Required for transfer items.')

        return cleaned_data


class TransferTransactionItemInline(admin.TabularInline):
    model  = TransactionItem
    form   = TransferTransactionItemForm
    extra  = 0
    fields = ['fund', 'direction', 'nominal']


@admin.register(TransferTransaction)
class TransferTransactionAdmin(BaseTransactionAdmin):
    _forced_direction = Transaction.Direction.TRANSFER
    inlines           = [TransferTransactionItemInline]
