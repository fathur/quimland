from django.contrib import admin
from ql.models import Wallet

@admin.register(Wallet)
class Wallet(admin.ModelAdmin):
    list_display    = ['name', 'kind']
    readonly_fields = ['balance', 'created_at', 'updated_at', 'deleted_at']

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {'fields': ['name', 'kind']}),
        ]
        if obj:
            fieldsets.append(('Audit', {'fields': ['created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}))
        return fieldsets