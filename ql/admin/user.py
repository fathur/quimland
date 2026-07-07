from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from ..models import PaymentBatch, Tariff, UserProperty


class UserPropertyInline(admin.StackedInline):
    model = UserProperty
    extra = 1
    max_num = 1
    can_delete = False


class TariffInline(admin.TabularInline):
    model = Tariff
    extra = 1
    fk_name = 'user'


class PaymentBatchInline(admin.TabularInline):
    model = PaymentBatch
    extra = 1
    fk_name = 'user'
    autocomplete_fields = ['creator']


class ExtendedUserAdmin(UserAdmin):
    inlines = list(UserAdmin.inlines) + [UserPropertyInline, TariffInline, PaymentBatchInline]


admin.site.unregister(User)
admin.site.register(User, ExtendedUserAdmin)
