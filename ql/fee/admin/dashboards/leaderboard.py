from django.contrib import admin
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from .data import resident_leaderboard


@permission_required('fee.view_alltransaction', raise_exception=True)
def leaderboard_dashboard_view(request):
    today = timezone.localdate()
    year  = today.year

    q = request.GET.get('q', '').strip()

    users_qs = User.objects.filter(is_active=True).select_related('properties')
    if q:
        users_qs = users_qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(username__icontains=q)
            | Q(properties__home_number__icontains=q)
        )

    rows = resident_leaderboard(users_qs, year, today=today)

    context = {
        **admin.site.each_context(request),
        'title': 'Leaderboard',
        'today': today,
        'year': year,
        'rows': rows,
        'total_residents': len(rows),
        'q': q,
    }
    return render(request, 'admin/leaderboard_dashboard.html', context)
