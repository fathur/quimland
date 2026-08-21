from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.db.models import Q, Sum
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html, mark_safe

from ql.fee.models import Fund, ItemRoutine, Receipt, Transaction, TransactionItem
from ql.fee.services.utils import fmt_rupiah
from ..filters import SoftDeleteAdminMixin, SoftDeleteFilter, make_date_range_filter, make_select_related_filter

OccurredAtRangeFilter = make_date_range_filter('occurred_at', 'occurred at')


class FundGroupedSelect(forms.Select):
    """Select widget that groups <option>s by Fund.kind using <optgroup>."""

    def optgroups(self, name, value, attrs=None):  # noqa: ARG002
        # Only open funds are offered for new selections, but a line item that
        # already points at a since-closed fund keeps showing it — otherwise
        # saving the form would silently reassign it to whatever option the
        # browser defaults to.
        selected_ids = {v for v in value if v}
        funds = Fund.objects.filter(
            Q(status=Fund.Status.OPEN) | Q(pk__in=selected_ids)
        ).order_by('kind', 'name')

        groups = {}
        for fund in funds:
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


class TransactionIconsMixin:
    """Shared QRIS/reconciled/receipt status icons for transaction admins."""

    @admin.display(description='Reconciled', ordering='is_reconciled')
    def reconciled_icon(self, obj):
        if not obj.is_reconciled:
            return ''
        return mark_safe(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
            ' stroke="#2563eb" stroke-width="2.5" stroke-linecap="round"'
            ' stroke-linejoin="round" width="16" height="16"'
            ' title="Reconciled" style="vertical-align:middle;">'
            '<path d="M20 6 9 17l-5-5"/>'
            '</svg>'
        )

    @admin.display(description='QRIS', ordering='is_qris')
    def qris_icon(self, obj):
        if not obj.is_qris:
            return ''
        return mark_safe(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
            ' stroke="currentColor" stroke-width="1.5" stroke-linecap="round"'
            ' stroke-linejoin="round" width="16" height="16"'
            ' title="QRIS" style="vertical-align:middle;color:var(--body-fg)">'
            '<path d="M3.75 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5'
            'c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 0 1 3.75 9.375v-4.5ZM3.75 14.625'
            'c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125'
            'h-4.5a1.125 1.125 0 0 1-1.125-1.125v-4.5ZM13.5 4.875c0-.621.504-1.125 1.125-1.125h4.5'
            'c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 0 1 13.5 9.375v-4.5Z"/>'
            '<path d="M6.75 6.75h.75v.75h-.75v-.75ZM6.75 16.5h.75v.75h-.75v-.75ZM16.5 6.75h.75v.75h-.75v-.75Z'
            'M13.5 13.5h.75v.75h-.75v-.75ZM13.5 19.5h.75v.75h-.75v-.75ZM19.5 13.5h.75v.75h-.75v-.75Z'
            'M19.5 19.5h.75v.75h-.75v-.75ZM16.5 16.5h.75v.75h-.75v-.75Z"/>'
            '</svg>'
        )

    @admin.display(description='', ordering='receipt')
    def receipt_icon(self, obj):
        if not obj.receipt or not obj.receipt.image:
            return ''
        url = reverse('admin:fee_receipt_change', args=[obj.receipt_id])
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
            url,
        )

    @admin.display(description='Transfer', ordering='transfer')
    def transfer_icon(self, obj):
        if not obj.transfer_id:
            return ''
        url = reverse('admin:fee_wallettransfer_change', args=[obj.transfer_id])
        return format_html(
            '<a href="{}" target="_blank" title="View transfer">'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
            ' stroke="currentColor" stroke-width="1.5" stroke-linecap="round"'
            ' stroke-linejoin="round" width="16" height="16"'
            ' style="vertical-align:middle;color:var(--body-fg)">'
            '<path d="M7.5 21 3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"/>'
            '</svg>'
            '</a>',
            url,
        )

    @admin.display(description='')
    def status_icons(self, obj):
        icons = [
            mark_safe(self.qris_icon(obj)),
            mark_safe(self.reconciled_icon(obj)),
            mark_safe(self.receipt_icon(obj)),
            mark_safe(self.transfer_icon(obj)),
        ]
        if not any(icons):
            return mark_safe('<div style="display:flex;gap:8px;align-items:center;justify-content:center;">—</div>')

        return format_html(
            '<div style="display:flex;gap:8px;align-items:center;justify-content:center;">{}{}{}{}</div>',
            *icons,
        )


class BaseTransactionAdmin(TransactionIconsMixin, SoftDeleteAdminMixin, admin.ModelAdmin):
    form                = TransactionAdminForm
    list_display        = ['id', 'user', 'wallet', 'nominal_display', 'occurred_at', 'receipt_icon', 'note_short']
    list_filter         = [SoftDeleteFilter, OccurredAtRangeFilter, 'wallet', ('user', make_select_related_filter('properties'))]
    search_fields       = ['id', 'user__username', 'user__first_name', 'user__last_name', 'note']
    ordering            = ['-occurred_at', '-created_at']
    autocomplete_fields = ['user']
    readonly_fields     = ['creator', 'created_at', 'updated_at', 'deleted_at', 'receipt_preview', 'transfer', 'direct_expense']

    _forced_direction = None

    actions = ['mark_qris', 'unmark_qris', 'mark_reconciled', 'unmark_reconciled', 'restore_selected']

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self.has_change_permission(request):
            for name in ('mark_qris', 'unmark_qris', 'mark_reconciled', 'unmark_reconciled', 'restore_selected'):
                actions.pop(name, None)
        if not self.has_delete_permission(request):
            actions.pop('delete_selected', None)
        return actions

    @admin.action(description='Restore selected')
    def restore_selected(self, request, queryset):
        if not self.has_change_permission(request):
            self.message_user(request, 'You do not have permission to restore records.', level='error')
            return
        # Looping obj.restore() (not the bulk queryset.restore()) routes
        # through Transaction.restore()'s cascade to items/sibling leg/transfer
        # — see delete_queryset() above for the same reasoning on the delete side.
        count = 0
        for obj in queryset:
            obj.restore()
            count += 1
        self.message_user(request, f'{count} record(s) restored.')

    @admin.action(description='Mark selected as QRIS')
    def mark_qris(self, request, queryset):
        updated = queryset.update(is_qris=True)
        self.message_user(request, f'{updated} transaction(s) marked as QRIS.')

    @admin.action(description='Unmark selected as QRIS')
    def unmark_qris(self, request, queryset):
        updated = queryset.update(is_qris=False)
        self.message_user(request, f'{updated} transaction(s) unmarked as QRIS.')

    @admin.action(description='Mark selected as reconciled')
    def mark_reconciled(self, request, queryset):
        updated = queryset.update(is_reconciled=True)
        self.message_user(request, f'{updated} transaction(s) marked as reconciled.')

    @admin.action(description='Unmark selected as reconciled')
    def unmark_reconciled(self, request, queryset):
        updated = queryset.update(is_reconciled=False)
        self.message_user(request, f'{updated} transaction(s) unmarked as reconciled.')

    

    def delete_queryset(self, request, queryset):
        # The "Delete selected" bulk action otherwise runs a raw queryset
        # UPDATE (SoftDeleteQuerySet.delete()), bypassing Transaction.delete()
        # and its cascade to items / sibling transfer legs.
        for obj in queryset:
            obj.delete()

    def has_change_permission(self, request, obj=None):
        if obj is not None and (obj.transfer_id or obj.direct_expense_id):
            return False
        return super().has_change_permission(request, obj)

    class Media:
        css = {'all': ['admin/css/transaction_highlight.css']}

    def get_fields(self, request, obj=None):
        fields = ['nominal', 'occurred_at', 'user', 'wallet', 'note', 'receipt_image', 'transfer', 'direct_expense']
        if obj and obj.receipt:
            fields.append('receipt_preview')
        if obj:
            fields += ['creator', 'created_at', 'updated_at', 'deleted_at']
        return fields

    def get_fieldsets(self, request, obj=None):
        fields = self.get_fields(request, obj)
        receipt_fields = ['receipt_image']
        if obj and obj.receipt:
            receipt_fields.insert(0, 'receipt_preview')
        other_fields = [f for f in fields if f not in ('receipt_image', 'receipt_preview', 'creator', 'created_at', 'updated_at', 'deleted_at')]
        fieldsets = [
            (None, {'fields': other_fields}),
            ('Receipt', {'fields': receipt_fields}),
        ]
        if obj:
            fieldsets.append(('Audit', {'fields': ['highlight', 'creator', 'created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}))
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
            cl = response.context_data['cl']
            total = cl.queryset.aggregate(total=Sum('nominal'))['total'] or Decimal('0')
            response.context_data['nominal_total'] = fmt_rupiah(total)
            # cl.result_count is the paginator's count of this same filtered
            # queryset — reuse it instead of running COUNT(*) a second time.
            response.context_data['nominal_total_count'] = cl.result_count
        except (AttributeError, KeyError):
            pass
        return response

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.get_object(request, object_id)
        if request.method == 'GET':
            self._check_nominal_mismatch(request, obj)
        return super().change_view(request, object_id, form_url, extra_context)

    def response_change(self, request, obj):
        if '_duplicate' in request.POST and self.has_add_permission(request):
            new_obj = self._duplicate_transaction(request, obj)
            self.message_user(request, f'Duplicated as transaction #{new_obj.pk}.')
            opts = self.model._meta
            url = reverse(f'admin:{opts.app_label}_{opts.model_name}_change', args=(new_obj.pk,))
            return HttpResponseRedirect(url)
        return super().response_change(request, obj)

    def _duplicate_transaction(self, request, obj):
        new_obj = Transaction.objects.get(pk=obj.pk)
        new_obj.pk         = None
        new_obj.id         = None
        new_obj._state.adding = True
        new_obj.creator    = request.user
        new_obj.receipt    = None
        new_obj.deleted_at = None
        new_obj.save()

        for item in TransactionItem.objects.filter(transaction=obj):
            old_item_pk        = item.pk
            item.pk            = None
            item.id            = None
            item._state.adding = True
            item.transaction   = new_obj
            item.save()
            routine = ItemRoutine.objects.filter(transaction_item_id=old_item_pk).first()
            if routine:
                ItemRoutine.objects.create(transaction_item=item, period=routine.period)

        return new_obj

    def save_formset(self, request, form, formset, change):  # noqa: ARG002
        if formset.model is not TransactionItem:
            super().save_formset(request, form, formset, change)
            return

        # _auto_dir = self._forced_direction if self._forced_direction != Transaction.Direction.TRANSFER else None
        _auto_dir = self._forced_direction
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
        short = (obj.note[:60] + '…') if len(obj.note) > 60 else obj.note
        return format_html('<span title="{}">{}</span>', obj.note, short)

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
