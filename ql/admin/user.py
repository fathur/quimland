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

    list_display = ['full_name', 'home_number', 'occupancy_status', 'phone', 'is_active', 'is_staff']
    ordering = ['first_name', 'last_name']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('properties')

    @admin.display(description='Full Name', ordering='first_name')
    def full_name(self, obj):
        return obj.get_full_name() or obj.username

    @admin.display(description='Home No.', ordering='properties__home_number')
    def home_number(self, obj):
        return getattr(obj, 'properties', None) and obj.properties.home_number or '—'

    @admin.display(description='Status', ordering='properties__occupancy_status')
    def occupancy_status(self, obj):
        prop = getattr(obj, 'properties', None)
        return prop.get_occupancy_status_display() if prop else '—'

    @admin.display(description='Phone', ordering='properties__phone')
    def phone(self, obj):
        return getattr(obj, 'properties', None) and obj.properties.phone or '—'

    def save_formset(self, request, _form, formset, change=False):
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk and hasattr(instance, 'creator_id') and not instance.creator_id:
                instance.creator = request.user
            instance.save()
        formset.save_m2m()


admin.site.unregister(User)
admin.site.register(User, ExtendedUserAdmin)
