from datetime import date as date_type
from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, Sum
from django.forms.models import BaseInlineFormSet
from django.utils.html import format_html

from ql.models import (
    Fund, IncomeTransaction, ExpenseTransaction, TransferTransaction,
    ItemRoutine, Receipt, Tariff, Transaction, TransactionItem,
)
from ql.utils import fmt_rupiah
from .filters import make_date_range_filter

OccurredAtRangeFilter = make_date_range_filter('occurred_at', 'occurred at')


class FundGroupedSelect(forms.Select):
    """Select widget that groups <option>s by Fund.kind using <optgroup>."""

    def optgroups(self, name, value, attrs=None):  # noqa: ARG002
        groups = {}
        for fund in Fund.objects.order_by('kind', 'name'):
            label = fund.get_kind_display()
            groups.setdefault(label, []).append((fund.pk, str(fund)))

        result = []
        for group_label, options in groups.items():
            subgroup = []
            for pk, display in options:
                subgroup.append(self.create_option(
                    name, pk, display, selected=str(pk) in value, index=len(result),
                ))
            result.append((group_label, subgroup, 0))
        return result


def _next_period(period):
    """'YYYY-MM' → the following month as 'YYYY-MM'."""
    y, m = map(int, period.split('-'))
    m += 1
    if m > 12:
        m, y = 1, y + 1
    return f'{y:04d}-{m:02d}'


class MonthPickerWidget(forms.TextInput):
    input_type = 'month'


# ── Income inline ─────────────────────────────────────────────────────────────

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


# ── Expense inline ────────────────────────────────────────────────────────────

class ExpenseTransactionItemForm(forms.ModelForm):
    class Meta:
        model   = TransactionItem
        fields  = ['fund', 'name', 'price', 'quantity', 'nominal']
        widgets = {'fund': FundGroupedSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quantity'].required = False
        self.fields['nominal'].required = False
        self.fields['fund'].label = 'Source of fund'

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

        if nominal is None and price is not None and quantity is not None:
            cleaned_data['nominal'] = price * quantity

        if cleaned_data.get('nominal') is None:
            self.add_error('nominal', 'Enter nominal, or fill both price and quantity.')

        return cleaned_data


class ExpenseTransactionItemInline(admin.TabularInline):
    model  = TransactionItem
    form   = ExpenseTransactionItemForm
    extra  = 0
    fields = ['fund', 'name', 'price', 'quantity', 'nominal']


# ── Transfer inline ───────────────────────────────────────────────────────────

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


# ── Header form (shared) ──────────────────────────────────────────────────────

class TransactionAdminForm(forms.ModelForm):
    receipt_image = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(),
        help_text='Upload a receipt image. Uploading a new file replaces the existing one.',
    )

    class Meta:
        model   = Transaction
        exclude = ['receipt', 'direction']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.receipt_id:
            try:
                self.fields['receipt_image'].initial = self.instance.receipt.image
            except Receipt.DoesNotExist:
                pass


# ── Base admin ────────────────────────────────────────────────────────────────

class BaseTransactionAdmin(admin.ModelAdmin):
    form                = TransactionAdminForm
    list_display        = ['id', 'user', 'wallet', 'nominal_display', 'occurred_at', 'receipt_icon', 'note_short']
    list_filter         = [OccurredAtRangeFilter, 'wallet', 'user']
    search_fields       = ['user__username', 'user__first_name', 'user__last_name', 'note']
    ordering            = ['-occurred_at', '-created_at']
    autocomplete_fields = ['user']
    readonly_fields     = ['creator', 'created_at', 'updated_at', 'receipt_preview']

    _forced_direction = None  # overridden by each subclass

    def get_queryset(self, request):
        return super().get_queryset(request).filter(direction=self._forced_direction)

    def get_fields(self, request, obj=None):
        fields = ['nominal', 'occurred_at', 'user', 'wallet', 'note', 'receipt_image']
        if obj and obj.receipt:
            fields.append('receipt_preview')
        if obj:
            fields += ['creator', 'created_at', 'updated_at']
        return fields

    def get_fieldsets(self, request, obj=None):
        fields = self.get_fields(request, obj)
        receipt_fields = ['receipt_image']
        if obj and obj.receipt:
            receipt_fields.insert(0, 'receipt_preview')
        other_fields = [f for f in fields if f not in ('receipt_image', 'receipt_preview', 'creator', 'created_at', 'updated_at')]
        fieldsets = [
            (None, {'fields': other_fields}),
            ('Receipt', {'fields': receipt_fields}),
        ]
        if obj:
            fieldsets.append(('Audit', {'fields': ['creator', 'created_at', 'updated_at'], 'classes': ['collapse']}))
        return fieldsets

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creator   = request.user
            obj.direction = self._forced_direction
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
                receipt.user_id = obj.user_id
                receipt.save()
            else:
                receipt = Receipt(user_id=obj.user_id, image=image)
                receipt.save()
                obj.receipt = receipt
                obj.save(update_fields=['receipt'])

    def _check_nominal_mismatch(self, request, obj):
        if obj and obj.pk:
            items_total = obj.items.aggregate(s=Sum('nominal'))['s'] or Decimal('0')
            if obj.nominal != items_total:
                diff = abs(obj.nominal - items_total)
                self.message_user(
                    request,
                    f'Warning: transaction nominal ({fmt_rupiah(obj.nominal)}) does not match '
                    f'the sum of items ({fmt_rupiah(items_total)}). '
                    f'Difference: {fmt_rupiah(diff)}.',
                    level=messages.WARNING,
                )

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.get_object(request, object_id)
        if request.method == 'GET':
            self._check_nominal_mismatch(request, obj)
        return super().change_view(request, object_id, form_url, extra_context)

    def save_formset(self, request, form, formset, change):  # noqa: ARG002
        if formset.model is not TransactionItem:
            # e.g. the Asset attachment formset — use default handling.
            super().save_formset(request, form, formset, change)
            return
        _auto_dir = self._forced_direction if self._forced_direction != Transaction.Direction.TRANSFER else None
        instances = formset.save(commit=False)
        for instance in instances:
            if _auto_dir:
                instance.direction = _auto_dir
            instance.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()
        self._check_nominal_mismatch(request, form.instance)

    @admin.display(description='Nominal', ordering='nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)

    @admin.display(description='Note')
    def note_short(self, obj):
        return (obj.note[:60] + '…') if len(obj.note) > 60 else obj.note

    @admin.display(description='', ordering='receipt')
    def receipt_icon(self, obj):
        if not obj.receipt or not obj.receipt.image:
            return '—'
        return format_html(
            '<a href="{}" target="_blank" title="View receipt">'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
            ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
            ' stroke-linejoin="round" width="16" height="16"'
            ' style="vertical-align:middle;color:var(--body-fg)">'
            '<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19'
            ' a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>'
            '</svg>'
            '</a>',
            obj.receipt.image.url,
        )

    @admin.display(description='Receipt preview')
    def receipt_preview(self, obj):
        if not obj or not obj.receipt or not obj.receipt.image:
            return '—'
        return format_html(
            '<a href="{}" target="_blank">'
            '<img src="{}" style="max-width:400px;max-height:400px;border-radius:8px;">'
            '</a>',
            obj.receipt.image.url, obj.receipt.image.url,
        )


# ── Proxy-model admins ────────────────────────────────────────────────────────

@admin.register(IncomeTransaction)
class IncomeTransactionAdmin(BaseTransactionAdmin):
    _forced_direction = Transaction.Direction.IN
    inlines           = [IncomeTransactionItemInline]
    list_display      = ['id', 'resident', 'wallet', 'nominal_display', 'occurred_at', 'receipt_icon', 'note_short']

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


@admin.register(ExpenseTransaction)
class ExpenseTransactionAdmin(BaseTransactionAdmin):
    _forced_direction   = Transaction.Direction.OUT
    inlines             = [ExpenseTransactionItemInline]
    list_display        = ['id', 'pic', 'wallet', 'nominal_display', 'occurred_at', 'receipt_icon', 'note_short']
    change_form_template = 'admin/ql/expensetransaction/change_form.html'

    @admin.display(description='PIC', ordering='user')
    def pic(self, obj):
        return obj.user

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['user'].label = 'PIC'
        return form

    def change_view(self, request, object_id, form_url='', extra_context=None):
        # Proofs attach to the concrete Transaction content type, so the same
        # asset manager works for any owning model in the future.
        ct = ContentType.objects.get_for_model(Transaction)
        extra_context = {
            **(extra_context or {}),
            'asset_content_type_id': ct.id,
            'asset_object_id': object_id,
            'asset_purpose': 'expense_proof',
        }
        return super().change_view(request, object_id, form_url, extra_context)


@admin.register(TransferTransaction)
class TransferTransactionAdmin(BaseTransactionAdmin):
    _forced_direction = Transaction.Direction.TRANSFER
    inlines           = [TransferTransactionItemInline]
