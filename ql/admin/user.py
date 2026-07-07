from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html

from ..models import PaymentBatch, Tariff, UserProperty


def _user_str(self):
    name = self.get_full_name() or self.username
    # Read from the ORM's __dict__ cache only — never issue an extra query.
    # properties is stored here when select_related('properties') was used.
    prop = self.__dict__.get('properties')
    home = (getattr(prop, 'home_number', '') or '') if prop is not None else ''
    return f'{name} ({home})' if home else name

User.__str__ = _user_str


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

    list_display = ['avatar', 'full_name', 'home_number', 'phone', 'occupancy_status', 'is_active']
    list_display_links = ['full_name']
    ordering = ['first_name', 'last_name']

    class Media:
        css = {'all': ['admin/css/user_changelist.css']}

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('properties')

    @admin.display(description='')
    def avatar(self, obj):
        name = obj.get_full_name() or obj.username
        initials = ''.join(p[0].upper() for p in name.split()[:2])
        hue = hash(name) % 360
        return format_html(
            '<div style="width:32px;height:32px;border-radius:50%;background:hsl({},55%,60%);"'
            ' title="{}">'
            '<span style="display:flex;align-items:center;justify-content:center;'
            'height:100%;font-size:12px;font-weight:700;color:#fff;">{}</span>'
            '</div>',
            hue, name, initials,
        )

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
        prop = getattr(obj, 'properties', None)
        number = prop.phone if prop else ''
        if not number:
            return '—'
        return format_html('<a href="https://wa.me/{}" target="_blank">{}</a>', number.lstrip('+'), number)

    def save_formset(self, request, _form, formset, change=False):
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk and hasattr(instance, 'creator_id') and not instance.creator_id:
                instance.creator = request.user
            instance.save()
        formset.save_m2m()


admin.site.unregister(User)
admin.site.register(User, ExtendedUserAdmin)
