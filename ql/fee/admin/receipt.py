from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html, mark_safe

from ql.fee.models import Receipt, Transaction
from ql.fee.services.utils import fmt_rupiah
from .mixins import LazyMediaGridAdmin


@admin.register(Receipt)
class ReceiptAdmin(LazyMediaGridAdmin, admin.ModelAdmin):
    list_display  = ['id', 'user', 'storage', 'image_preview', 'created_at']
    list_filter   = ['storage']
    list_per_page = 12
    readonly_fields = ['storage', 'user', 'created_at', 'updated_at', 'deleted_at', 'image', 'image_preview', 'related_records']
    search_fields = ['id', 'user__username', 'user__first_name', 'user__last_name']

    grid_fragment_template = 'admin/fee/receipt/_grid_items.html'

    class Media:
        css = {'all': ['admin/css/media_grid.css']}
        js = ['admin/js/media_grid.js']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'user__properties')

    def get_grid_image_url(self, obj):
        # obj.image.url is expensive for R2-backed receipts (~100ms — boto3
        # bootstraps a client and signs the URL on first real use); see
        # LazyMediaGridAdmin for why this is fetched lazily instead of
        # rendered inline for every row.
        return obj.image.url if obj.image else None

    def get_fields(self, request, obj=None):
        if obj:
            return ['user', 'image', 'image_preview', 'storage', 'related_records', 'created_at', 'updated_at', 'deleted_at']
        return ['user', 'image']

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {'fields': ['user', 'image', 'image_preview', 'storage']}),
        ]
        if obj:
            fieldsets.append(('Used by', {'fields': ['related_records']}))
            fieldsets.append(('Audit', {'fields': ['created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}))
        return fieldsets

    @admin.display(description='Related records')
    def related_records(self, obj):
        # Transaction.receipt (OneToOneField) is the only relation onto
        # Receipt anywhere in the codebase — grep `models/*.py` for `'Receipt'`
        # to confirm before assuming there's more to show here.
        if not obj or not obj.pk:
            return '—'
        try:
            transaction = obj.transaction
        except Transaction.DoesNotExist:
            transaction = None

        if transaction is None:
            return mark_safe('<span style="color:var(--body-quiet-color);">Not linked to any transaction.</span>')

        url = reverse('admin:fee_alltransaction_change', args=[transaction.pk])
        deleted_note = mark_safe(' <span style="color:#b91c1c;">(deleted)</span>') if transaction.deleted_at else ''
        return format_html(
            '<a href="{}">Transaction #{} — {} {}</a>{}',
            url, transaction.pk, transaction.get_direction_display(), fmt_rupiah(transaction.nominal), deleted_note,
        )

    @admin.display(description='Preview')
    def image_preview(self, obj):
        if not obj or not obj.image:
            return '—'
        url = obj.image.url
        return format_html(
            '<a href="{}" target="_blank">'
            '<img src="{}" style="max-width:400px;max-height:400px;border-radius:8px;">'
            '</a>',
            url, url,
        )

    def save_model(self, request, obj, form, change):
        if not change and not obj.user_id:
            obj.user_id = request.user.pk
        super().save_model(request, obj, form, change)
