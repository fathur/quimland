from django.contrib import admin
from ql.models import Wallet

@admin.register(Wallet)
class Wallet(admin.ModelAdmin):
    list_display  = ['name', 'kind', 'balance']
    readonly_fields = ['balance']