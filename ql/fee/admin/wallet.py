from django.contrib import admin
from ql.fee.models import Wallet

@admin.register(Wallet)
class Wallet(admin.ModelAdmin):
    list_display    = ['name', 'kind', 'is_blur']
    readonly_fields = ['balance', 'created_at', 'updated_at', 'deleted_at']

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {'fields': ['name', 'kind', 'is_blur']}),
        ]
        if obj:
            fieldsets.append(('Audit', {'fields': ['created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}))
        return fieldsets