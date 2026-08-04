from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from .data import resident_outstanding
from ql.fee.services.utils import fmt_rupiah


@permission_required('fee.view_alltransaction', raise_exception=True)
def outstanding_dashboard_view(request):
    today = timezone.localdate()

    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', '-total')

    users_qs = User.objects.filter(is_active=True).select_related('properties')
    if q:
        users_qs = users_qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(username__icontains=q)
            | Q(properties__home_number__icontains=q)
        )

    rows, funds = resident_outstanding(users_qs, today=today)

    sort_key = {
        'name': lambda r: r['name'].lower(),
        'home': lambda r: r['home_number'] or '',
        'total': lambda r: r['total'],
    }.get(sort.lstrip('-'), lambda r: r['total'])
    rows.sort(key=sort_key, reverse=sort.startswith('-'))

    grand_total = sum((r['total'] for r in rows), Decimal('0'))

    context = {
        **admin.site.each_context(request),
        'title': 'Outstanding Payments',
        'today': today,
        'funds': funds,
        'rows': rows,
        'total_residents': len(rows),
        'grand_total_display': fmt_rupiah(grand_total),
        'q': q,
        'sort': sort,
    }
    return render(request, 'admin/outstanding_dashboard.html', context)
