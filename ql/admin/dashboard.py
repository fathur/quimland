from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from ..models import CashEntry, Fund, FundDue, ItemRoutine, Tariff
from ..utils import fmt_rupiah


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def _year_tariff_map(year):
    """Returns get_nominal(user_id, fund_id, month_date) for all ROUTINE tariffs in the year."""
    year_start = date(year, 1, 1)
    year_end   = date(year, 12, 31)
    qs = (
        Tariff.objects
        .filter(fund__kind=Fund.Kind.ROUTINE, start_from__lte=year_end)
        .filter(Q(end_to__isnull=True) | Q(end_to__gte=year_start))
        .order_by('user_id', 'fund_id', '-start_from')
    )
    by_key = {}
    for t in qs:
        by_key.setdefault((t.user_id, t.fund_id), []).append(t)

    def get_nominal(user_id, fund_id, month_date):
        for t in by_key.get((user_id, fund_id), []):
            if t.start_from <= month_date and (t.end_to is None or t.end_to >= month_date):
                return t.nominal
        return None

    return get_nominal


def _year_paid_map(year):
    """
    {(user_id, fund_id, period): {'total': Decimal, 'entries': [{'occurred_at': dt, 'amount': Decimal}]}}
    One entry per distinct transaction, ordered by occurred_at ascending.
    """
    rows = (
        ItemRoutine.objects
        .filter(period__gte=f'{year}-01', period__lte=f'{year}-12')
        .filter(transaction_item__transaction__direction='IN')
        .filter(transaction_item__fund__kind=Fund.Kind.ROUTINE)
        .filter(transaction_item__transaction__user__is_active=True)
        .values(
            'transaction_item__transaction__user_id',
            'transaction_item__fund_id',
            'period',
            'transaction_item__transaction_id',
            'transaction_item__transaction__occurred_at',
        )
        .annotate(amount=Sum('transaction_item__nominal'))
        .order_by('transaction_item__transaction__occurred_at')
    )
    result = {}
    zero = Decimal('0')
    for r in rows:
        key = (
            r['transaction_item__transaction__user_id'],
            r['transaction_item__fund_id'],
            r['period'],
        )
        if key not in result:
            result[key] = {'total': zero, 'entries': []}
        amt = r['amount'] or zero
        result[key]['total'] += amt
        result[key]['entries'].append({
            'occurred_at': r['transaction_item__transaction__occurred_at'],
            'amount': amt,
            'transaction_id': r['transaction_item__transaction_id'],
        })
    return result


def _dot_status(amount, expected):
    if expected is None:
        return 'na'
    if amount >= expected:
        return 'paid'
    if amount > 0:
        return 'partial'
    return 'unpaid'


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------
def payments_dashboard_view(request):
    year   = timezone.localdate().year
    months = [date(year, m, 1) for m in range(1, 13)]

    funds      = list(Fund.objects.filter(kind=Fund.Kind.ROUTINE).order_by('name'))
    get_tariff = _year_tariff_map(year)
    paid       = _year_paid_map(year)

    users = list(
        User.objects.filter(is_active=True)
        .select_related('properties')
        .order_by('first_name', 'last_name', 'username')
    )

    zero = Decimal('0')
    rows = []
    for user in users:
        month_cells = []
        for month_date in months:
            period = month_date.strftime('%Y-%m')
            dots = []
            for fund in funds:
                expected = get_tariff(user.id, fund.id, month_date)
                data     = paid.get((user.id, fund.id, period))
                total    = data['total'] if data else zero
                status   = _dot_status(total, expected)

                if data and data['entries']:
                    badges = [
                        {'occurred_at': e['occurred_at'], 'status': status, 'transaction_id': e['transaction_id']}
                        for e in data['entries']
                    ]
                elif status == 'na':
                    badges = []
                else:
                    badges = [{'occurred_at': None, 'status': 'unpaid'}]

                dots.append({'fund': fund, 'status': status, 'badges': badges})
            month_cells.append({'month': month_date.month, 'dots': dots})

        rows.append({
            'user': user,
            'name': str(user),
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
    }
    return render(request, 'admin/payments_dashboard.html', context)


# ===========================================================================
# Earmarked fund tracking dashboard
# ===========================================================================
def _parse_as_of(value):
    """Parse a YYYY-MM-DD 'simulate history' cutoff; None means 'up to now'."""
    if not value:
        return None
    try:
        return date(int(value[:4]), int(value[5:7]), int(value[8:10]))
    except (ValueError, IndexError):
        return None


def _cmp_status(actual, reference):
    """Compare actual vs a reference amount → Kurang / Pas / Lebih.

    Returns None when there is no reference to compare against (e.g. a fund with
    no target set).
    """
    if reference is None:
        return None
    if actual < reference:
        return {'code': 'kurang', 'label': 'Kurang'}
    if actual > reference:
        return {'code': 'lebih', 'label': 'Lebih'}
    return {'code': 'pas', 'label': 'Pas'}


def earmarked_dashboard_view(request):
    funds = list(
        Fund.objects
        .filter(kind=Fund.Kind.EARMARKED)
        .order_by('-status', 'name')  # OPEN before CLOSED, then alphabetical
    )

    selected_id = request.GET.get('fund')
    selected = None
    if selected_id:
        selected = next((f for f in funds if str(f.id) == selected_id), None)
    if selected is None and funds:
        selected = funds[0]

    as_of = _parse_as_of(request.GET.get('as_of'))

    context = {
        **admin.site.each_context(request),
        'title': 'Earmarked Funds',
        'funds': funds,
        'selected': selected,
        'as_of': as_of.strftime('%Y-%m-%d') if as_of else '',
        'as_of_label': as_of.strftime('%d %b %Y') if as_of else None,
        'today': timezone.localdate().strftime('%Y-%m-%d'),
    }

    if selected is None:
        return render(request, 'admin/earmarked_dashboard.html', context)

    # ---- Cash flow (respecting the as_of cutoff) ----
    entries = CashEntry.objects.filter(fund=selected)
    if as_of:
        entries = entries.filter(occurred_at__date__lte=as_of)

    zero = Decimal('0')
    collected = entries.filter(direction=CashEntry.Direction.IN).aggregate(s=Sum('amount'))['s'] or zero
    spent = entries.filter(direction=CashEntry.Direction.OUT).aggregate(s=Sum('amount'))['s'] or zero
    balance = collected - spent

    total_expected = FundDue.objects.filter(fund=selected).aggregate(s=Sum('expected_amount'))['s'] or zero
    target = selected.target_amount  # may be None

    has_dues = FundDue.objects.filter(fund=selected).exists()

    # ---- Per-person breakdown (dues OUTER-JOIN contributions) ----
    expected_map = {
        uid: amt
        for uid, amt in FundDue.objects.filter(fund=selected).values_list('user_id', 'expected_amount')
    }
    paid_map = {
        r['user_id']: r['total']
        for r in (
            entries.filter(direction=CashEntry.Direction.IN)
            .exclude(user_id=None)
            .values('user_id')
            .annotate(total=Sum('amount'))
        )
    }

    user_ids = set(expected_map) | set(paid_map)
    users = {u.id: u for u in User.objects.filter(id__in=user_ids)}

    counts = {'kurang': 0, 'pas': 0, 'lebih': 0, 'sukarela': 0}
    people = []
    for uid in user_ids:
        user = users.get(uid)
        expected = expected_map.get(uid, zero)
        paid = paid_map.get(uid, zero)
        diff = paid - expected
        voluntary = uid not in expected_map  # never billed → a voluntary giver
        status = _cmp_status(paid, expected)

        counts[status['code']] += 1
        if voluntary:
            counts['sukarela'] += 1

        people.append({
            'user': user,
            'name': (user.get_full_name() or user.username) if user else f'User #{uid}',
            'expected': expected,
            'paid': paid,
            'diff': diff,
            'expected_display': fmt_rupiah(expected),
            'paid_display': fmt_rupiah(paid),
            'diff_display': fmt_rupiah(abs(diff)),
            'diff_sign': '−' if diff < 0 else ('+' if diff > 0 else ''),
            'status': status,
            'voluntary': voluntary,
        })

    # Biggest shortfalls first, then by name — the treasurer's default question.
    people.sort(key=lambda p: (p['diff'], p['name'].lower()))

    context.update({
        'target': target,
        'target_display': fmt_rupiah(target) if target is not None else None,
        'total_expected': total_expected,
        'total_expected_display': fmt_rupiah(total_expected),
        'collected': collected,
        'collected_display': fmt_rupiah(collected),
        'spent_display': fmt_rupiah(spent),
        'balance_display': fmt_rupiah(balance),
        'balance_negative': balance < 0,
        'status_vs_target': _cmp_status(collected, target),
        'status_vs_expected': _cmp_status(collected, total_expected) if has_dues else None,
        'target_pct': int(min(collected / target, 1) * 100) if target else None,
        'has_dues': has_dues,
        'people': people,
        'counts': counts,
        'total_people': len(people),
    })
    return render(request, 'admin/earmarked_dashboard.html', context)


# ---------------------------------------------------------------------------
# Register the pages on the default admin site (namespace: admin)
# ---------------------------------------------------------------------------
_original_get_urls = admin.site.get_urls


def _get_urls():
    return [
        path(
            'payments-dashboard/',
            admin.site.admin_view(payments_dashboard_view),
            name='payments_dashboard',
        ),
        path(
            'earmarked-dashboard/',
            admin.site.admin_view(earmarked_dashboard_view),
            name='earmarked_dashboard',
        ),
    ] + _original_get_urls()


admin.site.get_urls = _get_urls


# ---------------------------------------------------------------------------
# Inject "Dashboard" group into the admin sidebar (available_apps)
# ---------------------------------------------------------------------------
_DASHBOARD_APP = {
    'name': 'Dashboard',
    'app_label': 'ql_dashboard',
    'app_url': '/admin/payments-dashboard/',
    'has_module_perms': True,
    'models': [
        {
            'name': 'Transactions',
            'object_name': 'TransactionsDashboard',
            'admin_url': '/admin/payments-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        },
        {
            'name': 'Earmarked funds',
            'object_name': 'EarmarkedDashboard',
            'admin_url': '/admin/earmarked-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        },
        {
            'name': 'Scan Receipt',
            'object_name': 'ReceiptScan',
            'admin_url': '/admin/receipt-scan/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        },
    ],
}

_original_each_context = admin.site.__class__.each_context


def _each_context(self, request):
    ctx = _original_each_context(self, request)
    ctx['available_apps'] = [_DASHBOARD_APP] + list(ctx.get('available_apps', []))
    return ctx


admin.site.__class__.each_context = _each_context
