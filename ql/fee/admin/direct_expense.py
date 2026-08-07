from django import forms
from django.contrib import admin
from django.forms.models import BaseInlineFormSet
from django.urls import reverse
from django.utils.html import format_html

from ql.fee.models import DirectExpense, Receipt, Transaction, TransactionItem
from ql.fee.services.utils import fmt_rupiah
from .transaction.base import OccurredAtRangeFilter
from .transaction.expense import ExpenseTransactionItemForm


class DirectExpenseItemFormSet(BaseInlineFormSet):
    """TransactionItem's FK points at Transaction, not DirectExpense (the
    admin's registered model) — so the `instance` the admin machinery hands
    us here is actually the grandparent. Re-target it to the expense leg
    before the base class builds its filtered queryset / FK-assignment
    logic off of it."""

    def __init__(self, data=None, files=None, instance=None, save_as_new=False,
                 prefix=None, queryset=None, **kwargs):
        expense_tx = instance.expense_transaction if instance and instance.pk else None
        super().__init__(
            data=data, files=files, instance=expense_tx, save_as_new=save_as_new,
            prefix=prefix, queryset=queryset, **kwargs,
        )


class DirectExpenseItemInline(admin.TabularInline):
    # Entered once, in the expense leg's shape (fund/name/price/quantity) —
    # DirectExpenseAdmin.save_formset() mirrors these onto the income leg.
    model   = TransactionItem
    form    = ExpenseTransactionItemForm
    formset = DirectExpenseItemFormSet
    fk_name = 'transaction'
    extra   = 0
    fields  = ['fund', 'name', 'price', 'quantity', 'nominal']


class DirectExpenseAdminForm(forms.ModelForm):
    receipt_image = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(),
        help_text='Uploaded to the expense leg. Uploading a new file replaces the existing one.',
    )

    class Meta:
        model  = DirectExpense
        fields = ['user', 'occurred_at', 'note']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.expense_transaction_id:
            receipt = self.instance.expense_transaction.receipt
            if receipt:
                self.fields['receipt_image'].initial = receipt.image


@admin.register(DirectExpense)
class DirectExpenseAdmin(admin.ModelAdmin):
    form                = DirectExpenseAdminForm
    # Deliberately NOT using the declarative `inlines` attribute: Django's
    # admin system check (admin.E202) validates every entry there against
    # `fk_name` being a FK *on DirectExpense*, but TransactionItem's FK
    # targets Transaction. get_inline_instances() below builds these by hand
    # instead, so the check framework never sees them.
    _item_inline_classes = [DirectExpenseItemInline]
    list_display        = ['id', 'occurred_at', 'user', 'nominal_display', 'note_short']
    list_filter         = [OccurredAtRangeFilter]
    search_fields       = [
        'id', 'note',
        'user__username', 'user__first_name', 'user__last_name',
    ]
    ordering            = ['-occurred_at', '-created_at']
    autocomplete_fields = ['user']
    readonly_fields     = [
        'nominal_display', 'income_transaction_link', 'expense_transaction_link', 'receipt_preview',
        'creator', 'created_at', 'updated_at',
    ]

    def get_inline_instances(self, request, obj=None):
        # Build each inline against Transaction, not self.model (DirectExpense)
        # — TransactionItem's FK targets Transaction, so inlineformset_factory
        # needs Transaction as parent_model to resolve it. DirectExpenseItemFormSet
        # then re-targets `instance` to obj.expense_transaction (see its __init__).
        # This mirrors ModelAdmin.get_inline_instances(), just swapping which
        # model gets passed as parent_model.
        instances = []
        for inline_class in self._item_inline_classes:
            inline = inline_class(Transaction, self.admin_site)
            if request:
                if not (
                    inline.has_view_or_change_permission(request, obj)
                    or inline.has_add_permission(request, obj)
                    or inline.has_delete_permission(request, obj)
                ):
                    continue
                if not inline.has_add_permission(request, obj):
                    inline.max_num = 0
            instances.append(inline)
        return instances

    def get_fields(self, request, obj=None):
        fields = ['user', 'occurred_at', 'note', 'receipt_image']
        if obj:
            fields += [
                'nominal_display', 'income_transaction_link', 'expense_transaction_link',
                'creator', 'created_at', 'updated_at',
            ]
        return fields

    def get_fieldsets(self, request, obj=None):
        fields = self.get_fields(request, obj)
        receipt_fields = ['receipt_image']
        if obj and obj.expense_transaction.receipt_id:
            receipt_fields.insert(0, 'receipt_preview')
        excluded = set(receipt_fields) | {
            'creator', 'created_at', 'updated_at',
            'nominal_display', 'income_transaction_link', 'expense_transaction_link',
        }
        other_fields = [f for f in fields if f not in excluded]
        fieldsets = [
            (None, {'fields': other_fields}),
            ('Receipt', {'fields': receipt_fields}),
        ]
        if obj:
            fieldsets.append(('Legs', {'fields': ['nominal_display', 'income_transaction_link', 'expense_transaction_link']}))
            fieldsets.append(('Audit', {'fields': ['creator', 'created_at', 'updated_at'], 'classes': ['collapse']}))
        return fieldsets

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creator = request.user
        super().save_model(request, obj, form, change)  # obj.save() creates/updates both legs

        image = form.cleaned_data.get('receipt_image')
        expense_tx = obj.expense_transaction
        if image is False:
            if expense_tx.receipt_id:
                old = expense_tx.receipt
                expense_tx.receipt = None
                expense_tx.save(update_fields=['receipt'])
                old.delete()
        elif image:
            if expense_tx.receipt_id:
                receipt = expense_tx.receipt
                receipt.image = image
                receipt.user_id = obj.user_id
                receipt.save()
            else:
                receipt = Receipt(user_id=obj.user_id, image=image)
                receipt.save()
                expense_tx.receipt = receipt
                expense_tx.save(update_fields=['receipt'])

    def save_formset(self, request, form, formset, change):  # noqa: ARG002
        if formset.model is not TransactionItem:
            super().save_formset(request, form, formset, change)
            return

        obj = form.instance  # DirectExpense — save_model() above already gave it both legs
        instances = formset.save(commit=False)
        for instance in instances:
            instance.transaction = obj.expense_transaction
            instance.save()
        for deleted in formset.deleted_objects:
            deleted.delete()
        formset.save_m2m()
        obj.sync_legs()

    def delete_queryset(self, request, queryset):
        # Bulk queryset.delete() would bypass DirectExpense.delete()'s cascade
        # to both legs — see BaseTransactionAdmin.delete_queryset for the same
        # reasoning.
        for obj in queryset:
            obj.delete()

    @admin.display(description='Income leg')
    def income_transaction_link(self, obj):
        if not obj or not obj.income_transaction_id:
            return '—'
        url = reverse('admin:fee_incometransaction_change', args=[obj.income_transaction_id])
        return format_html('<a href="{}">Income #{}</a>', url, obj.income_transaction_id)

    @admin.display(description='Expense leg')
    def expense_transaction_link(self, obj):
        if not obj or not obj.expense_transaction_id:
            return '—'
        url = reverse('admin:fee_expensetransaction_change', args=[obj.expense_transaction_id])
        return format_html('<a href="{}">Expense #{}</a>', url, obj.expense_transaction_id)

    @admin.display(description='Nominal', ordering='nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)

    @admin.display(description='Note')
    def note_short(self, obj):
        return format_html('<span title="{}">{}</span>', obj.note, (obj.note[:60] + '…') if len(obj.note) > 60 else obj.note)

    @admin.display(description='Receipt preview')
    def receipt_preview(self, obj):
        receipt = obj.expense_transaction.receipt if obj and obj.expense_transaction_id else None
        if not receipt or not receipt.image:
            return '—'
        return format_html(
            '<a href="{}" target="_blank">'
            '<img src="{}" style="max-width:400px;max-height:400px;border-radius:8px;">'
            '</a>',
            receipt.image.url, receipt.image.url,
        )
