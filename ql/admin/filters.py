from datetime import datetime

from django.contrib import admin
from django.utils import timezone


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
