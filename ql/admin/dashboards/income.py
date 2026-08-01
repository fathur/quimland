from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from .data import dot_status, year_note_map, year_paid_map, year_tariff_map
from ql.models import Fund
from ql.services.utils import fmt_rupiah


@permission_required('ql.view_alltransaction', raise_exception=True)
def income_dashboard_view(request):
    today        = timezone.localdate()
    year         = today.year
    current_month = today.month
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
    month_fund_totals = {(fund.id, month_date.strftime('%Y-%m')): zero for fund in funds for month_date in months}
    month_fund_applicable = {(fund.id, month_date.strftime('%Y-%m')): False for fund in funds for month_date in months}
    month_fund_paid_count = {(fund.id, month_date.strftime('%Y-%m')): 0 for fund in funds for month_date in months}

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

                if status != 'na':
                    month_fund_totals[(fund.id, period)] += total
                    month_fund_applicable[(fund.id, period)] = True
                    if status == 'paid':
                        month_fund_paid_count[(fund.id, period)] += 1

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

                if status != "na":
                    dots.append({'fund': fund, 'status': status, 'badges': badges})
            month_cells.append({'month': month_date.month, 'dots': dots})

        rows.append({
            'user': user,
            'name': user.get_full_name() or user.username,
            'home_number': home,
            'month_cells': month_cells,
        })

    summary_cells = []
    for month_date in months:
        period = month_date.strftime('%Y-%m')
        fund_totals = [
            {
                'fund': fund,
                'total_display': fmt_rupiah(month_fund_totals[(fund.id, period)]),
                'paid_count': month_fund_paid_count[(fund.id, period)],
            }
            for fund in funds
            if month_fund_applicable[(fund.id, period)]
        ]
        summary_cells.append({'month': month_date.month, 'fund_totals': fund_totals})

    future_months = [m for m in months if m.month > current_month]
    future_periods = {m.strftime('%Y-%m') for m in future_months}
    fund_future_totals = {fund.id: zero for fund in funds}

    for (user_id, fund_id, period), data in paid.items():
        if period not in future_periods or fund_id not in fund_future_totals:
            continue
        month_date = date(year, int(period[5:7]), 1)
        expected   = get_tariff(user_id, fund_id, month_date)
        if dot_status(data['total'], expected) == 'na':
            continue
        fund_future_totals[fund_id] += data['total']

    fund_by_id = {fund.id: fund for fund in funds}
    future_savings = sorted(
        (
            {'fund': fund_by_id[fid], 'total_display': fmt_rupiah(total)}
            for fid, total in fund_future_totals.items()
            if total > zero
        ),
        key=lambda entry: entry['fund'].name,
    )
    future_savings_total_display = fmt_rupiah(sum(fund_future_totals.values(), zero))
    future_range_display = None
    if future_months:
        future_range_display = f'{future_months[0]:%b} – {future_months[-1]:%b} {year}'

    context = {
        **admin.site.each_context(request),
        'title': 'Income',
        'year': year,
        'months': months,
        'funds': funds,
        'rows': rows,
        'summary_cells': summary_cells,
        'total_users': len(rows),
        'current_month': current_month,
        'future_savings': future_savings,
        'future_savings_total_display': future_savings_total_display,
        'future_range_display': future_range_display,
        'q': q,
        'sort': sort,
    }
    return render(request, 'admin/income_dashboard.html', context)
