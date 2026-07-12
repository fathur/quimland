from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from ql.models import CashEntry, DueNote, Fund, FundDue, ItemRoutine, Tariff, Transaction, TransactionItem, Wallet
from ql.utils import fmt_rupiah


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


def _year_note_map(year):
    """{(user_id, fund_id, period): {'id', 'reason', 'reason_label', 'note'}} for the year."""
    rows = (
        DueNote.objects
        .filter(period__gte=f'{year}-01', period__lte=f'{year}-12')
        .annotate(_proof_count=Count('proofs'))
    )
    return {
        (n.user_id, n.fund_id, n.period): {
            'id': n.id,
            'reason': n.reason,
            'reason_label': n.get_reason_display(),
            'note': n.note,
            'has_proof': n._proof_count > 0,
        }
        for n in rows
    }


def _fund_money_map():
    """
    {fund_id: {'collected': Decimal, 'spent': Decimal, 'balance': Decimal}}

    'collected' sums every IN line item, 'spent' sums every OUT line item, using
    each item's *effective* direction — its own direction for TRANSFER legs, else
    the parent transaction's direction (IN/OUT items leave it null and inherit).
    """
    rows = (
        TransactionItem.objects
        .annotate(eff_dir=Coalesce('direction', 'transaction__direction'))
        .values('fund_id', 'eff_dir')
        .annotate(total=Sum('nominal'))
    )
    zero = Decimal('0')
    result = {}
    for r in rows:
        bucket = result.setdefault(
            r['fund_id'], {'collected': zero, 'spent': zero, 'balance': zero}
        )
        amount = r['total'] or zero
        if r['eff_dir'] == 'IN':
            bucket['collected'] += amount
        elif r['eff_dir'] == 'OUT':
            bucket['spent'] += amount
    for bucket in result.values():
        bucket['balance'] = bucket['collected'] - bucket['spent']
    return result


def _wallet_money_map():
    """
    {wallet_id: {'in': Decimal, 'out': Decimal, 'balance': Decimal}}

    Sums every transaction that carries a wallet, by the transaction's own
    direction. Wallet transfers land here as their split IN/OUT legs (see
    WalletTransfer.save), so a transfer debits the source wallet and credits
    the destination without any special handling.
    """
    rows = (
        Transaction.objects
        .filter(wallet_id__isnull=False)
        .values('wallet_id', 'direction')
        .annotate(total=Sum('nominal'))
    )
    zero = Decimal('0')
    result = {}
    for r in rows:
        bucket = result.setdefault(
            r['wallet_id'], {'in': zero, 'out': zero, 'balance': zero}
        )
        amount = r['total'] or zero
        if r['direction'] == Transaction.Direction.IN:
            bucket['in'] += amount
        elif r['direction'] == Transaction.Direction.OUT:
            bucket['out'] += amount
    for bucket in result.values():
        bucket['balance'] = bucket['in'] - bucket['out']
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
    notes      = _year_note_map(year)

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
                status   = _dot_status(total, expected)

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


# ===========================================================================
# Funds overview dashboard — one card per fund, grouped by kind
# ===========================================================================
def funds_dashboard_view(request):
    money = _fund_money_map()
    zero  = Decimal('0')

    # OPEN before CLOSED within each kind, then alphabetical.
    funds = list(Fund.objects.order_by('-status', 'name'))

    total_balance = zero
    groups = {}  # kind value -> [card dict, ...]
    for fund in funds:
        m         = money.get(fund.id, {'collected': zero, 'spent': zero, 'balance': zero})
        collected = m['collected']
        balance   = m['balance']
        total_balance += balance

        card = {
            'fund': fund,
            'is_open': fund.status == Fund.Status.OPEN,
            'is_earmarked': fund.kind == Fund.Kind.EARMARKED,
            'collected_display': fmt_rupiah(collected),
            'spent_display': fmt_rupiah(m['spent']),
            'balance_display': fmt_rupiah(balance),
            'balance_negative': balance < 0,
            'target_display': fmt_rupiah(fund.target_amount) if fund.target_amount else None,
            'progress_pct': None,
        }
        if fund.kind == Fund.Kind.EARMARKED and fund.target_amount:
            card['progress_pct'] = int(min(collected / fund.target_amount, 1) * 100)

        groups.setdefault(fund.kind, []).append(card)

    # Section order follows Fund.Kind declaration order; skip empty kinds.
    sections = [
        {'label': label, 'cards': groups[value]}
        for value, label in Fund.Kind.choices
        if groups.get(value)
    ]

    context = {
        **admin.site.each_context(request),
        'title': 'Funds',
        'total_balance_display': fmt_rupiah(total_balance),
        'total_balance_negative': total_balance < 0,
        'sections': sections,
        'fund_count': len(funds),
    }
    return render(request, 'admin/funds_dashboard.html', context)


# ===========================================================================
# Wallets overview dashboard — one card per wallet
# ===========================================================================
def wallet_dashboard_view(request):
    money = _wallet_money_map()
    zero  = Decimal('0')

    wallets = list(Wallet.objects.order_by('name'))

    total_balance = zero
    cards = []
    for wallet in wallets:
        m       = money.get(wallet.id, {'in': zero, 'out': zero, 'balance': zero})
        balance = m['balance']
        total_balance += balance

        cards.append({
            'wallet': wallet,
            'kind_display': wallet.get_kind_display(),
            'in_display': fmt_rupiah(m['in']),
            'out_display': fmt_rupiah(m['out']),
            'balance_display': fmt_rupiah(balance),
            'balance_negative': balance < 0,
        })

    context = {
        **admin.site.each_context(request),
        'title': 'Wallets',
        'total_balance_display': fmt_rupiah(total_balance),
        'total_balance_negative': total_balance < 0,
        'cards': cards,
        'wallet_count': len(wallets),
    }
    return render(request, 'admin/wallet_dashboard.html', context)


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
            'funds-dashboard/',
            admin.site.admin_view(funds_dashboard_view),
            name='funds_dashboard',
        ),
        path(
            'wallet-dashboard/',
            admin.site.admin_view(wallet_dashboard_view),
            name='wallet_dashboard',
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
            'name': 'Funds overview',
            'object_name': 'FundsDashboard',
            'admin_url': '/admin/funds-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        },
        {
            'name': 'Wallets overview',
            'object_name': 'WalletDashboard',
            'admin_url': '/admin/wallet-dashboard/',
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
