from datetime import date as date_type

from django import forms
from django.contrib import admin
from django.db.models import Q
from django.forms.models import BaseInlineFormSet

from ql.models import IncomeTransaction, ItemRoutine, Tariff, Transaction, TransactionItem
from .base import BaseTransactionAdmin, FundGroupedSelect, MonthPickerWidget


def _next_period(period):
    """'YYYY-MM' → the following month as 'YYYY-MM'."""
    y, m = map(int, period.split('-'))
    m += 1
    if m > 12:
        m, y = 1, y + 1
    return f'{y:04d}-{m:02d}'


class IncomeTransactionItemForm(forms.ModelForm):
    period = forms.CharField(
        required=False,
        widget=MonthPickerWidget(),
        help_text='YYYY-MM — fill for routine (monthly/garbage) payments only.',
    )

    class Meta:
        model   = TransactionItem
        fields  = ['fund', 'nominal', 'period']
        widgets = {'fund': FundGroupedSelect}

    _transaction = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nominal'].required = False
        if self.instance and self.instance.pk:
            routine = ItemRoutine.objects.filter(transaction_item=self.instance).first()
            if routine:
                self.fields['period'].initial = routine.period

    def clean(self):
        cleaned_data = super().clean()
        txn        = self._transaction
        fund       = cleaned_data.get('fund')
        nominal    = cleaned_data.get('nominal')
        period_str = (cleaned_data.get('period') or '').strip()
        self._period_was_blank = not period_str

        if not fund:
            return cleaned_data

        user_id = getattr(txn, 'user_id', None)
        tariff  = None
        if user_id:
            if period_str:
                try:
                    ref_date = date_type.fromisoformat(f'{period_str}-01')
                except ValueError:
                    ref_date = date_type.today()
            else:
                ref_date = date_type.today()
            tariff = (
                Tariff.objects
                .filter(user_id=user_id, fund=fund, start_from__lte=ref_date)
                .filter(Q(end_to__isnull=True) | Q(end_to__gte=ref_date))
                .order_by('-start_from')
                .first()
            )

        if nominal is None:
            if tariff:
                cleaned_data['nominal'] = tariff.nominal
            elif user_id:
                self.add_error(
                    'nominal',
                    'No active tariff found for this fund/user/period. Enter amount manually.',
                )
            else:
                self.add_error('nominal', 'This field is required.')

        if not period_str and user_id:
            latest = (
                ItemRoutine.objects
                .filter(
                    transaction_item__fund=fund,
                    transaction_item__transaction__user_id=user_id,
                )
                .order_by('-period')
                .values_list('period', flat=True)
                .first()
            )
            if latest:
                cleaned_data['period'] = _next_period(latest)
            elif tariff:
                cleaned_data['period'] = tariff.start_from.strftime('%Y-%m')

        return cleaned_data


class IncomeTransactionItemFormSet(BaseInlineFormSet):
    """Hand out consecutive months to sibling rows of the same fund."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        cursor_by_fund = {}
        for form in self.forms:
            cd = getattr(form, 'cleaned_data', None)
            if not cd or cd.get('DELETE'):
                continue
            fund = cd.get('fund')
            if not fund:
                continue

            period = (cd.get('period') or '').strip()
            if getattr(form, '_period_was_blank', False):
                cursor = cursor_by_fund.get(fund.id) or period
                if cursor:
                    cd['period'] = cursor
                    cursor_by_fund[fund.id] = _next_period(cursor)
            elif period:
                cursor_by_fund[fund.id] = _next_period(period)


class IncomeTransactionItemInline(admin.TabularInline):
    model   = TransactionItem
    form    = IncomeTransactionItemForm
    formset = IncomeTransactionItemFormSet
    extra   = 0
    fields  = ['fund', 'nominal', 'period']

    def get_formset(self, request, obj=None, **kwargs):
        FormSet = super().get_formset(request, obj, **kwargs)

        if obj is not None:
            _txn = obj
        elif request.method == 'POST':
            user_pk = request.POST.get('user', '')
            _txn = type('_TxnProxy', (), {
                'direction': Transaction.Direction.IN,
                'user_id': int(user_pk) if user_pk.isdigit() else None,
            })()
        else:
            _txn = None

        OriginalForm = FormSet.form

        class BoundForm(OriginalForm):
            _transaction = _txn

        BoundForm.__name__ = OriginalForm.__name__
        FormSet.form = BoundForm
        return FormSet


@admin.register(IncomeTransaction)
class IncomeTransactionAdmin(BaseTransactionAdmin):
    _forced_direction = Transaction.Direction.IN
    inlines           = [IncomeTransactionItemInline]
    list_display      = ['id', 'occurred_at', 'wallet', 'nominal_display', 'resident', 'receipt_icon', 'note_short', 'highlight_row']



    @admin.display(description='Resident', ordering='user')
    def resident(self, obj):
        return obj.user

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['user'].label = 'Resident'
        return form

    def save_formset(self, request, form, formset, change):
        if formset.model is not TransactionItem:
            super(BaseTransactionAdmin, self).save_formset(request, form, formset, change)
            return
        instances = formset.save(commit=False)
        for instance in instances:
            instance.direction = Transaction.Direction.IN
            instance.save()
        for form_instance in formset.forms:
            if hasattr(form_instance, 'instance') and form_instance.instance.pk:
                period = form_instance.cleaned_data.get('period', '').strip()
                if period:
                    ItemRoutine.objects.update_or_create(
                        transaction_item=form_instance.instance,
                        defaults={'period': period},
                    )
                else:
                    ItemRoutine.objects.filter(transaction_item=form_instance.instance).delete()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()
        self._check_nominal_mismatch(request, form.instance)
