from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from ..models import CashEntry, Fund, FundDue, Payment, Tariff
from ..utils import fmt_rupiah


# ---------------------------------------------------------------------------
# Month helpers
# ---------------------------------------------------------------------------
def _parse_month(value):
    """First day of the requested YYYY-MM, defaulting to the current month."""
    today = timezone.localdate()
    if value:
        try:
            return date(int(value[:4]), int(value[5:7]), 1)
        except (ValueError, IndexError):
            pass
    return date(today.year, today.month, 1)


def _shift_month(d, delta):
    """Return the first day of the month `delta` months away from `d`."""
    index = d.year * 12 + (d.month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def _tariff_map(period_date):
    """{(user_id, kind): nominal} — the active tariff for the given month.

    Mirrors the resolution used in PaymentBatchAdmin.tariff_lookup_view: a tariff
    with a null end_to is active through the end of the current calendar year.
    """
    end_of_year = date(date.today().year, 12, 31)

    qs = (
        Tariff.objects
        .filter(start_from__lte=period_date)
        .filter(Q(end_to__isnull=True) | Q(end_to__gte=period_date))
        .order_by('user_id', 'kind', '-start_from')
    )
    if period_date > end_of_year:
        qs = qs.filter(end_to__isnull=False)

    result = {}
    for tariff in qs:
        key = (tariff.user_id, tariff.kind)
        if key not in result:  # ordering guarantees the most recent tariff first
            result[key] = tariff.nominal
    return result


def _paid_map(period):
    """{(user_id, kind): total_paid} for the YYYY-MM period, across all batches."""
    rows = (
        Payment.objects
        .filter(period=period, batch__user__is_active=True)
        .values('batch__user_id', 'kind')
        .annotate(total=Sum('nominal'))
    )
    return {(r['batch__user_id'], r['kind']): r['total'] for r in rows}


def _status(paid, expected):
    """Classify a single (paid vs. expected) cell."""
    if expected is None:
        return {'code': 'na', 'label': 'No tariff'}
    if paid >= expected:
        return {'code': 'paid', 'label': 'Paid'}
    if paid > 0:
        return {'code': 'partial', 'label': 'Partial'}
    return {'code': 'unpaid', 'label': 'Unpaid'}


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------
def payments_dashboard_view(request):
    period_date = _parse_month(request.GET.get('month'))
    period = period_date.strftime('%Y-%m')

    tariffs = _tariff_map(period_date)
    paid = _paid_map(period)

    users = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')

    empty = lambda: {'paid': 0, 'partial': 0, 'unpaid': 0, 'na': 0, 'collected': 0, 'expected': 0}
    summary = {'monthly': empty(), 'garbage': empty()}

    rows = []
    for user in users:
        cells = {}
        for skey, kind in (('monthly', Payment.Kind.MONTHLY), ('garbage', Payment.Kind.GARBAGE)):
            expected = tariffs.get((user.id, kind))
            amount = paid.get((user.id, kind), 0) or 0
            status = _status(amount, expected)

            cells[skey] = {
                'status': status,
                'paid': amount,
                'paid_display': fmt_rupiah(amount),
                'expected_display': fmt_rupiah(expected) if expected is not None else '—',
            }

            bucket = summary[skey]
            bucket[status['code']] += 1
            bucket['collected'] += amount
            if expected is not None:
                bucket['expected'] += expected

        rows.append({
            'user': user,
            'name': user.get_full_name() or user.username,
            'monthly': cells['monthly'],
            'garbage': cells['garbage'],
        })

    for bucket in summary.values():
        bucket['collected_display'] = fmt_rupiah(bucket['collected'])
        bucket['expected_display'] = fmt_rupiah(bucket['expected'])

    context = {
        **admin.site.each_context(request),
        'title': 'Payments Dashboard',
        'period': period,
        'period_label': period_date.strftime('%B %Y'),
        'prev_month': _shift_month(period_date, -1).strftime('%Y-%m'),
        'next_month': _shift_month(period_date, +1).strftime('%Y-%m'),
        'current_month': timezone.localdate().strftime('%Y-%m'),
        'is_current': period == timezone.localdate().strftime('%Y-%m'),
        'rows': rows,
        'summary': summary,
        'total_users': len(rows),
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
            'name': 'Payments',
            'object_name': 'PaymentsDashboard',
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
