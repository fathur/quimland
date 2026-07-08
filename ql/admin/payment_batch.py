from datetime import date

from admin_auto_filters.filters import AutocompleteFilter
from django import forms
from django.contrib import admin, messages
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html
from ql.utils import fmt_rupiah

from ..models import Payment, PaymentBatch, Tariff


class UserFilter(AutocompleteFilter):
    title = 'User'
    field_name = 'user'

LOCK_AFTER_DAYS = 20



class MonthPickerWidget(forms.TextInput):
    input_type = 'month'


class PaymentInlineForm(forms.ModelForm):
    nominal = forms.DecimalField(
        required=False, max_digits=15, decimal_places=2,
        help_text='Leave blank to auto-fill from the active tariff.',
    )
    period = forms.CharField(
        required=False, widget=MonthPickerWidget(),
        help_text='Leave blank to use the month after the last recorded payment.',
    )

    class Meta:
        model = Payment
        fields = '__all__'
        widgets = {'period': MonthPickerWidget()}


class PaymentInline(admin.TabularInline):
    model = Payment
    form = PaymentInlineForm
    extra = 1
    ordering = ['kind', '-period']


@admin.register(PaymentBatch)
class PaymentBatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'paid_at', 'nominal_display', 'receipt_icon', 'note']
    list_filter = [UserFilter, 'paid_at']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    ordering = ['-paid_at']
    autocomplete_fields = ['user']
    inlines = [PaymentInline]

    class Media:
        ...
        # js = ('ql/js/payment_inline.js',)

    # def get_urls(self):
    #     return [
    #         path(
    #             'tariff-lookup/',
    #             self.admin_site.admin_view(self.tariff_lookup_view),
    #             name='payment_tariff_lookup',
    #         ),
    #     ] + super().get_urls()

    # def tariff_lookup_view(self, request):
        # user_id = request.GET.get('user_id')
        # kind = request.GET.get('kind')
        # period = request.GET.get('period')  # YYYY-MM

        # if not all([user_id, kind, period]):
        #     return JsonResponse({'nominal': None, 'warning': None})

        # try:
        #     period_date = date(int(period[:4]), int(period[5:7]), 1)
        # except (ValueError, IndexError):
        #     return JsonResponse({'nominal': None, 'warning': None})

        # end_of_year = date(date.today().year, 12, 31)

        # tariffs = (
        #     Tariff.objects
        #     .filter(user_id=user_id, kind=kind, start_from__lte=period_date)
        #     .filter(Q(end_to__isnull=False, end_to__gte=period_date) | Q(end_to__isnull=True))
        #     .order_by('-start_from')
        # )
        # # null end_to means "active through end of this year" — exclude if period is beyond that
        # if period_date > end_of_year:
        #     tariffs = tariffs.filter(end_to__isnull=False)

        # count = tariffs.count()
        # if count == 0:
        #     return JsonResponse({'nominal': None, 'warning': None})

        # tariff = tariffs.first()
        # warning = (
        #     f'{count} overlapping tariffs found for this user/kind/period; '
        #     f'using the most recent one (Rp {tariff.nominal:,}).'
        #     if count >= 2 else None
        # )
        # return JsonResponse({'nominal': str(tariff.nominal), 'warning': warning})

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user__properties')

    @admin.display(description='Nominal', ordering='nominal')
    def nominal_display(self, obj):
        return fmt_rupiah(obj.nominal)

    @admin.display(description='', ordering='receipt')
    def receipt_icon(self, obj):
        if not obj.receipt:
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
            obj.receipt.url,
        )
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.get_object(request, object_id)
        if obj:
            payments_total = obj.payments.aggregate(total=Sum('nominal'))['total'] or 0
            if obj.nominal != payments_total:
                messages.warning(
                    request,
                    f'Batch nominal ({fmt_rupiah(obj.nominal)}) does not match '
                    f'the sum of its payments ({fmt_rupiah(payments_total)}). '
                    f'Please review the payment entries.',
                )
        return super().change_view(request, object_id, form_url, extra_context)

    def _is_locked(self, obj):
        if obj is None:
            return False
        return (timezone.now() - obj.created_at).days >= LOCK_AFTER_DAYS

    def has_change_permission(self, request, obj=None):
        if self._is_locked(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._is_locked(obj):
            return False
        return super().has_delete_permission(request, obj)

    def get_fields(self, request, obj=None):
        exclude = {'creator', 'created_at', 'receipt', 'receipt_preview'}
        fields = [f for f in super().get_fields(request, obj) if f not in exclude]
        if obj:
            fields += ['creator', 'created_at']
        return fields

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        receipt_fields = ['receipt']
        if obj and obj.receipt:
            receipt_fields.insert(0, 'receipt_preview')
        fieldsets.append(('Receipt', {'fields': receipt_fields}))
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        ro = []
        if obj and obj.receipt:
            ro += ['receipt_preview']
        if obj:
            ro += ['creator', 'created_at']
        return ro

    @admin.display(description='Receipt preview')
    def receipt_preview(self, obj):
        if not obj or not obj.receipt:
            return '—'
        return format_html(
            '<a href="{}" target="_blank">'
            '<img src="{}" style="max-width:400px;max-height:400px;border-radius:8px;">'
            '</a>',
            obj.receipt.url, obj.receipt.url,
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creator = request.user
        super().save_model(request, obj, form, change)
