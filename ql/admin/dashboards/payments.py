from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from .data import dot_status, year_note_map, year_paid_map, year_tariff_map
from ql.models import Fund


def payments_dashboard_view(request):
    year   = timezone.localdate().year
    months = [date(year, m, 1) for m in range(1, 13)]

    funds      = list(Fund.objects.filter(kind=Fund.Kind.ROUTINE).order_by('name'))
    get_tariff = year_tariff_map(year)
    paid       = year_paid_map(year)
    notes      = year_note_map(year)

    q    = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'name')

    users_qs = User.objects.filter(is_active=True).select_related('properties')

    if q:
        users_qs = users_qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(username__icontains=q)
            | Q(properties__home_number__icontains=q)
        )

    if sort in ('home', '-home'):
        prefix = '-' if sort == '-home' else ''
        users_qs = users_qs.order_by(
            f'{prefix}properties__home_number',
            f'{prefix}first_name',
            f'{prefix}last_name',
        )
    elif sort == '-name':
        users_qs = users_qs.order_by('-first_name', '-last_name', '-username')
    else:
        users_qs = users_qs.order_by('first_name', 'last_name', 'username')

    zero = Decimal('0')
    rows = []
    for user in users_qs:
        prop = getattr(user, 'properties', None)
        home = (getattr(prop, 'home_number', '') or '') if prop is not None else ''

        month_cells = []
        for month_date in months:
            period = month_date.strftime('%Y-%m')
            dots = []
            for fund in funds:
                expected = get_tariff(user.id, fund.id, month_date)
                data     = paid.get((user.id, fund.id, period))
                total    = data['total'] if data else zero
                status   = dot_status(total, expected)

                if data and data['entries']:
                    badges = [
                        {'occurred_at': e['occurred_at'], 'status': status, 'transaction_id': e['transaction_id']}
                        for e in data['entries']
                    ]
                elif status == 'na':
                    badges = []
                else:
                    badges = [{
                        'occurred_at': None,
                        'status': 'unpaid',
                        'period': period,
                        'note': notes.get((user.id, fund.id, period)),
                    }]

                dots.append({'fund': fund, 'status': status, 'badges': badges})
            month_cells.append({'month': month_date.month, 'dots': dots})

        rows.append({
            'user': user,
            'name': user.get_full_name() or user.username,
            'home_number': home,
            'month_cells': month_cells,
        })

    context = {
        **admin.site.each_context(request),
        'title': 'Transactions',
        'year': year,
        'months': months,
        'funds': funds,
        'rows': rows,
        'total_users': len(rows),
        'current_month': timezone.localdate().month,
        'q': q,
        'sort': sort,
    }
    return render(request, 'admin/payments_dashboard.html', context)
