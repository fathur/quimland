from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.core.validators import RegexValidator
from django.shortcuts import redirect, render
from django.utils import timezone

from ql.fee.models import Fund, RoutinePayout
from ql.fee.services.pass_through import (
    collected_by_period,
    pass_through_ledger,
    paid_by_period,
    payable_items,
    period_of,
)
from ql.fee.services.utils import fmt_rupiah

PERIOD_RE = r'^\d{4}-(0[1-9]|1[0-2])$'


class RoutinePayoutForm(forms.Form):
    period = forms.CharField(
        label='Period',
        validators=[RegexValidator(PERIOD_RE, 'Use YYYY-MM.')],
        widget=forms.TextInput(attrs={'type': 'month'}),
    )
    amount = forms.DecimalField(
        label='Payout', max_digits=15, decimal_places=2, min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'step': 'any', 'placeholder': '0', 'inputmode': 'decimal'}),
    )
    transaction_item = forms.ModelChoiceField(
        label='Expense item', queryset=None, empty_label='Select an expense item…',
    )

    def __init__(self, *args, fund, today, **kwargs):
        super().__init__(*args, **kwargs)
        self.fund = fund
        self.today = today
        self.fields['period'].initial = period_of(today)
        # Future months are held — stop the month picker at the current month.
        self.fields['period'].widget.attrs['max'] = period_of(today)
        item_field = self.fields['transaction_item']
        item_field.queryset = payable_items(fund)
        item_field.label_from_instance = lambda item: (
            f'#{item.transaction_id} · '
            f'{timezone.localtime(item.transaction.occurred_at):%d %b %Y}'
            f'{" · " + item.name if item.name else ""}'
            f' · unallocated {fmt_rupiah(item.unallocated)}'
        )

    def clean_period(self):
        period = self.cleaned_data['period']
        if period > period_of(self.today):
            raise forms.ValidationError('Money collected in advance is held — it can only be paid out from its own month.')
        return period

    def clean(self):
        cleaned = super().clean()
        period, amount, item = cleaned.get('period'), cleaned.get('amount'), cleaned.get('transaction_item')
        if period and amount and item:
            if amount > item.unallocated:
                self.add_error('amount', f'Only {fmt_rupiah(item.unallocated)} of this expense item is still unallocated.')
            collected = collected_by_period(self.fund).get(period, {'total': Decimal('0')})['total']
            remaining = collected - paid_by_period(self.fund).get(period, Decimal('0'))
            if amount > remaining:
                self.add_error('amount', f'Only {fmt_rupiah(max(remaining, Decimal("0")))} is left to pay out for {period}.')
        return cleaned


@permission_required('fee.view_alltransaction', raise_exception=True)
def garbage_dashboard_view(request):
    fund = Fund.objects.filter(is_pass_through=True).order_by('id').first()
    today = timezone.localdate()
    can_edit = request.user.has_perm('fee.add_expensetransaction')

    form = None
    if fund and request.method == 'POST':
        if not can_edit:
            raise PermissionDenied
        delete_id = request.POST.get('delete_id')
        if delete_id:
            payout = RoutinePayout.objects.filter(pk=delete_id, transaction_item__fund=fund).first()
            if payout:
                payout.delete()
                messages.success(request, f'Allocation for {payout.period} removed.')
            return redirect('admin:garbage_dashboard')
        form = RoutinePayoutForm(request.POST, fund=fund, today=today)
        if form.is_valid():
            RoutinePayout.objects.create(
                transaction_item=form.cleaned_data['transaction_item'],
                period=form.cleaned_data['period'],
                amount=form.cleaned_data['amount'],
            )
            messages.success(request, f'Payout of {fmt_rupiah(form.cleaned_data["amount"])} allocated to {form.cleaned_data["period"]}.')
            return redirect('admin:garbage_dashboard')
    elif fund and can_edit:
        form = RoutinePayoutForm(fund=fund, today=today)

    context = {
        **admin.site.each_context(request),
        'title': 'Garbage Payouts',
        'fund': fund,
        'form': form,
        'can_edit': can_edit,
    }
    if fund:
        ledger = pass_through_ledger(fund, today)
        context.update({
            'rows': list(reversed(ledger['rows'])),
            'collected_display': fmt_rupiah(ledger['collected_total']),
            'paid_display': fmt_rupiah(ledger['paid_total']),
            'due_now_display': fmt_rupiah(ledger['due_now']),
            'held_display': fmt_rupiah(ledger['held']),
            'has_held': ledger['held'] != 0,
            'current_period': period_of(today),
        })
        if form is not None:
            # Drives the form's live hints and payout autofill (see the template's script).
            unallocated = {str(item.pk): str(item.unallocated) for item in form.fields['transaction_item'].queryset}
            context['has_payable_items'] = bool(unallocated)
            context['form_config'] = {
                'current': period_of(today),
                'remaining': {r['period']: str(max(r['remaining'], Decimal('0'))) for r in ledger['rows'] if not r['is_held']},
                'unallocated': unallocated,
            }
    return render(request, 'admin/garbage_dashboard.html', context)
