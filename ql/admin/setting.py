from django.contrib import admin

from ql.models import Setting


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ['key', 'value']
    search_fields = ['key']
