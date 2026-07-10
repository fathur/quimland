from django import forms
from django.contrib import admin
from django.utils.html import format_html

from ..models import ItemRoutine, Receipt, Transaction, TransactionItem
from ..utils import fmt_rupiah


class MonthPickerWidget(forms.TextInput):
    input_type = 'month'


class TransactionItemInlineForm(forms.ModelForm):
    period = forms.CharField(
        required=False,
        widget=MonthPickerWidget(),
        help_text='YYYY-MM — fill for routine (monthly/garbage) payments only.',
    )

    class Meta:
        model  = TransactionItem
        fields = ['fund', 'direction', 'nominal', 'loan', 'period']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate period from the related ItemRoutine if editing an existing item.
        if self.instance and self.instance.pk:
            routine = ItemRoutine.objects.filter(transaction_item=self.instance).first()
            if routine:
                self.fields['period'].initial = routine.period

    def save(self, commit=True):
        item = super().save(commit=commit)
        period = self.cleaned_data.get('period', '').strip()
        if commit and item.pk:
            if period:
                ItemRoutine.objects.update_or_create(
                    transaction_item=item,
                    defaults={'period': period},
                )
            else:
                ItemRoutine.objects.filter(transaction_item=item).delete()
        return item


class TransactionItemInline(admin.TabularInline):
    model      = TransactionItem
    form       = TransactionItemInlineForm
    extra      = 1
    fields     = ['fund', 'direction', 'nominal', 'loan', 'period']
    autocomplete_fields = ['fund']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display   = ['id', 'direction', 'user', 'nominal_display', 'occurred_at', 'receipt_icon', 'note_short']
    list_filter    = ['direction', 'occurred_at']
    search_fields  = ['user__username', 'user__first_name', 'user__last_name', 'note']
    ordering       = ['-occurred_at', '-created_at']
    autocomplete_fields = ['user', 'receipt']
    readonly_fields = ['creator', 'created_at', 'updated_at', 'receipt_preview']
    inlines        = [TransactionItemInline]

    def get_fields(self, request, obj=None):
        fields = ['direction', 'nominal', 'occurred_at', 'user', 'note', 'receipt']
        if obj and obj.receipt:
            fields.append('receipt_preview')
        if obj:
            fields += ['creator', 'created_at', 'updated_at']
        return fields

    def get_fieldsets(self, request, obj=None):
        fields = self.get_fields(request, obj)
        receipt_fields = ['receipt']
        if obj and obj.receipt:
            receipt_fields.insert(0, 'receipt_preview')
        other_fields = [f for f in fields if f not in ('receipt', 'receipt_preview', 'creator', 'created_at', 'updated_at')]
        fieldsets = [
            (None, {'fields': other_fields}),
            ('Receipt', {'fields': receipt_fields}),
        ]
        if obj:
            fieldsets.append(('Audit', {'fields': ['creator', 'created_at', 'updated_at'], 'classes': ['collapse']}))
        return fieldsets

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creator = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        # Persist TransactionItem instances first so they have a PK,
        # then let the inline form's save() handle ItemRoutine.
        instances = formset.save(commit=False)
        for instance in instances:
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

    # ── display helpers ──────────────────────────────────────────────────────

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
