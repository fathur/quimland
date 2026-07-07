from django.contrib import admin

from ..models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['batch', 'kind', 'period', 'nominal']
    list_filter = ['kind', 'period']
    ordering = ['period']
