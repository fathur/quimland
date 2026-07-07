from django.contrib import admin

from ..models import Tariff


@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ['user', 'kind', 'nominal', 'start_from', 'end_to']
    list_filter = ['kind']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    ordering = ['user', 'kind', 'start_from']
    autocomplete_fields = ['user']
