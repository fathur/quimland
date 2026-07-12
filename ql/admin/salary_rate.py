from django.contrib import admin

from ql.models import SalaryRate


@admin.register(SalaryRate)
class SalaryRateAdmin(admin.ModelAdmin):
    list_display = ['payee', 'amount', 'start_from', 'end_to']
    list_filter = ['payee']
    ordering = ['start_from']
