from datetime import datetime

from django.contrib import admin
from django.utils import timezone


class SoftDeleteFilter(admin.SimpleListFilter):
    """
    Three-way filter: Active (default) / All / Deleted.
    Requires the admin's get_queryset to return objects.with_deleted().
    """
    title = 'status'
    parameter_name = 'deleted'

    def lookups(self, request, model_admin):
        return [
            ('active',  'Active'),
            ('all',     'All'),
            ('deleted', 'Deleted'),
        ]

    def queryset(self, request, queryset):
        v = self.value()
        if v == 'deleted':
            return queryset.filter(deleted_at__isnull=False)
        if v == 'all':
            return queryset
        return queryset.filter(deleted_at__isnull=True)

    def choices(self, changelist):
        for lookup, title in self.lookup_choices:
            is_default = self.value() is None and lookup == 'active'
            yield {
                'selected':     self.value() == str(lookup) or is_default,
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display':      title,
            }


class SoftDeleteAdminMixin:
    """
    Mix into any ModelAdmin whose model extends TimestampMixin to expose
    soft-deleted records via SoftDeleteFilter.

    Usage:
        class MyAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
            list_filter = [SoftDeleteFilter, ...]
            actions = ['restore_selected', ...]

            @admin.action(description='Restore selected')
            def restore_selected(self, request, queryset):
                restored = queryset.restore()
                self.message_user(request, f'{restored} record(s) restored.')
    """

    def get_queryset(self, request):
        qs = self.model.objects.with_deleted()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs


def make_select_related_filter(*related_fields):
    """
    Return a RelatedFieldListFilter subclass that select_related()s the given
    fields when building the sidebar choice list.

    Django's default RelatedFieldListFilter.field_choices() fetches the full
    related queryset with no select_related and calls str() on every row —
    if that model's __str__ touches a relation (e.g. User's __str__ touching
    `properties`), that's one extra query per row, every time the changelist
    renders. This produces the exact same choices/labels, just via a JOIN
    instead of N+1 separate queries.

    Usage:
        list_filter = [..., ('user', make_select_related_filter('properties'))]
    """
    class _SelectRelatedFieldListFilter(admin.RelatedFieldListFilter):
        def field_choices(self, field, request, model_admin):
            ordering = self.field_admin_ordering(field, request, model_admin)
            rel_model = field.remote_field.model
            qs = rel_model._default_manager.complex_filter(field.get_limit_choices_to())
            qs = qs.select_related(*related_fields)
            if ordering:
                qs = qs.order_by(*ordering)
            return [(x.pk, str(x)) for x in qs]

    return _SelectRelatedFieldListFilter


def make_date_range_filter(field_name, title=None):
    """
    Return a SimpleListFilter subclass that filters a DateTimeField by a from/to
    datetime range using <input type="datetime-local"> widgets in the sidebar.

    Usage:
        @admin.register(MyModel)
        class MyAdmin(admin.ModelAdmin):
            list_filter = [make_date_range_filter('occurred_at', 'occurred at')]
    """
    gte_param = f'{field_name}__gte'
    lte_param = f'{field_name}__lte'
    filter_title = title or field_name.replace('_', ' ')

    class DateRangeFilter(admin.SimpleListFilter):
        parameter_name = gte_param
        template = 'admin/date_range_filter.html'

        def __init__(self, *args, **kwargs):
            self.title = filter_title
            super().__init__(*args, **kwargs)

        def lookups(self, request, model_admin):
            return (('_', '_'),)

        def queryset(self, request, queryset):
            dt_from = request.GET.get(gte_param, '').strip()
            dt_to   = request.GET.get(lte_param, '').strip()
            try:
                if dt_from:
                    dt = datetime.fromisoformat(dt_from)
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt)
                    queryset = queryset.filter(**{f'{field_name}__gte': dt})
                if dt_to:
                    dt = datetime.fromisoformat(dt_to)
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt)
                    queryset = queryset.filter(**{f'{field_name}__lte': dt})
            except ValueError:
                pass
            return queryset

        def choices(self, changelist):
            # Collect all current params except our own so the form can re-emit
            # them as hidden inputs, preserving other active filters on submit.
            other_params = [
                (k, v)
                for k, v in changelist.params.items()
                if k not in (gte_param, lte_param, 'p')
            ]
            yield {
                'date_from':    changelist.params.get(gte_param, ''),   # ISO datetime string
                'date_to':      changelist.params.get(lte_param, ''),   # ISO datetime string
                'query_string': changelist.get_query_string(remove=[gte_param, lte_param]),
                'gte_param':    gte_param,
                'lte_param':    lte_param,
                'other_params': other_params,
            }

    DateRangeFilter.__name__ = f'{field_name.title().replace("_", "")}DateRangeFilter'
    return DateRangeFilter
