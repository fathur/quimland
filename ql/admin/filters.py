from datetime import date as date_type

from django.contrib import admin


def make_date_range_filter(field_name, title=None):
    """
    Return a SimpleListFilter subclass that filters a DateTimeField by a from/to
    date range using native <input type="date"> widgets in the sidebar.

    Usage:
        @admin.register(MyModel)
        class MyAdmin(admin.ModelAdmin):
            list_filter = [make_date_range_filter('occurred_at', 'occurred at')]
    """
    gte_param = f'{field_name}__gte'
    lte_param = f'{field_name}__lte'
    filter_title = title or field_name.replace('_', ' ')

    class DateRangeFilter(admin.SimpleListFilter):
        # parameter_name just needs to be unique; real filtering uses gte/lte params.
        parameter_name = gte_param
        template = 'admin/date_range_filter.html'

        def __init__(self, *args, **kwargs):
            self.title = filter_title
            super().__init__(*args, **kwargs)

        def lookups(self, request, model_admin):
            # Must be non-empty for Django to render the filter block.
            return (('_', '_'),)

        def queryset(self, request, queryset):
            date_from = request.GET.get(gte_param, '').strip()
            date_to   = request.GET.get(lte_param, '').strip()
            try:
                if date_from:
                    queryset = queryset.filter(**{f'{field_name}__date__gte': date_type.fromisoformat(date_from)})
                if date_to:
                    queryset = queryset.filter(**{f'{field_name}__date__lte': date_type.fromisoformat(date_to)})
            except ValueError:
                pass
            return queryset

        def choices(self, changelist):
            yield {
                'date_from': changelist.params.get(gte_param, ''),
                'date_to':   changelist.params.get(lte_param, ''),
                'query_string': changelist.get_query_string(remove=[gte_param, lte_param]),
                'gte_param': gte_param,
                'lte_param': lte_param,
            }

    DateRangeFilter.__name__ = f'{field_name.title().replace("_", "")}DateRangeFilter'
    return DateRangeFilter
