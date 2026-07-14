from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.db.models import Sum
from django.utils.html import format_html

from ql.models import Fund, Receipt, Transaction, TransactionItem
from ql.utils import fmt_rupiah
from ..filters import make_date_range_filter

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


class MonthPickerWidget(forms.TextInput):
    input_type = 'month'


class TransactionAdminForm(forms.ModelForm):
    receipt_image = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(),
        help_text='Upload a receipt image. Uploading a new file replaces the existing one.',
    )

    class Meta:
        model   = Transaction
        exclude  = ['receipt', 'direction']
        widgets  = {'highlight': forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.receipt_id:
            try:
                self.fields['receipt_image'].initial = self.instance.receipt.image
            except Receipt.DoesNotExist:
                pass


class BaseTransactionAdmin(admin.ModelAdmin):
    form                = TransactionAdminForm
    list_display        = ['id', 'user', 'wallet', 'nominal_display', 'occurred_at', 'receipt_icon', 'note_short']
    list_filter         = [OccurredAtRangeFilter, 'wallet', 'user']
    search_fields       = ['id', 'user__username', 'user__first_name', 'user__last_name', 'note']
    ordering            = ['-occurred_at', '-created_at']
    autocomplete_fields = ['user']
    readonly_fields     = ['creator', 'created_at', 'updated_at', 'receipt_preview']

    _forced_direction = None

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .filter(direction=self._forced_direction)
            # .filter(transfer__isnull=True)
        )

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.transfer_id:
            return False
        return super().has_change_permission(request, obj)

    class Media:
        css = {'all': ['admin/css/transaction_highlight.css']}

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
            fieldsets.append(('Audit', {'fields': ['highlight', 'creator', 'created_at', 'updated_at'], 'classes': ['collapse']}))
        else:
            fieldsets.append(('Highlight', {'fields': ['highlight'], 'classes': ['collapse']}))
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

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data['cl'].queryset
            total = qs.aggregate(total=Sum('nominal'))['total'] or Decimal('0')
            response.context_data['nominal_total'] = fmt_rupiah(total)
            response.context_data['nominal_total_count'] = qs.count()
        except (AttributeError, KeyError):
            pass
        return response

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.get_object(request, object_id)
        if request.method == 'GET':
            self._check_nominal_mismatch(request, obj)
        return super().change_view(request, object_id, form_url, extra_context)

    def save_formset(self, request, form, formset, change):  # noqa: ARG002
        if formset.model is not TransactionItem:
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

    @admin.display(description='')
    def highlight_row(self, obj):
        if obj.highlight:
            return format_html('<span class="row-hl row-hl--{}" hidden></span>', obj.highlight)
        return ''

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
