from django.contrib import admin

from ..models import Payout


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ['payee', 'period', 'payout_date', 'amount', 'creator', 'note']
    list_filter = ['payee', 'period']
    search_fields = ['payee', 'period']
    ordering = ['payout_date', 'payee']
    autocomplete_fields = ['creator']
