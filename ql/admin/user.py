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
    exclude = ['creator']


class ExtendedUserAdmin(UserAdmin):
    inlines = list(UserAdmin.inlines) + [UserPropertyInline, TariffInline, PaymentBatchInline]

    def save_formset(self, request, _form, formset, _change):
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk and hasattr(instance, 'creator_id') and not instance.creator_id:
                instance.creator = request.user
            instance.save()
        formset.save_m2m()


admin.site.unregister(User)
admin.site.register(User, ExtendedUserAdmin)
