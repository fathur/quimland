from datetime import date, datetime
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from ql.models import DueNote, Fund, ItemRoutine, Tariff, Transaction, TransactionItem
from ql.utils import fmt_rupiah


def year_tariff_map(year):
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


def year_paid_map(year):
    """
    {(user_id, fund_id, period): {'total': Decimal, 'entries': [{'occurred_at', 'amount', 'transaction_id'}]}}
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


def year_note_map(year):
    """{(user_id, fund_id, period): {'id', 'reason', 'reason_label', 'note', 'has_proof'}} for the year."""
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


def parse_as_of_dt(value):
    """Parse a datetime-local string (YYYY-MM-DDTHH:MM[:SS]) into an aware datetime."""
    if not value:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d'):
        try:
            return timezone.make_aware(datetime.strptime(value, fmt))
        except ValueError:
            continue
    return None


def parse_as_of_date(value):
    """Parse a YYYY-MM-DD 'simulate history' cutoff; None means 'up to now'."""
    if not value:
        return None
    try:
        return date(int(value[:4]), int(value[5:7]), int(value[8:10]))
    except (ValueError, IndexError):
        return None


def fund_money_map(as_of=None):
    """
    {fund_id: {'collected': Decimal, 'spent': Decimal, 'balance': Decimal}}
    Pass as_of (aware datetime) to restrict to transactions up to that point.
    """
    qs = (
        TransactionItem.objects
        .filter(transaction__deleted_at__isnull=True, fund__deleted_at__isnull=True)
        .annotate(eff_dir=Coalesce('direction', 'transaction__direction'))
    )
    if as_of:
        qs = qs.filter(transaction__occurred_at__lte=as_of)
    rows = qs.values('fund_id', 'eff_dir').annotate(total=Sum('nominal'))
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


def wallet_money_map(as_of=None):
    """
    {wallet_id: {'in': Decimal, 'out': Decimal, 'balance': Decimal}}

    Wallet transfer IN/OUT legs are included so wallet balances move correctly.
    Pass as_of (aware datetime) to restrict to transactions up to that point.
    """
    qs = Transaction.objects.filter(wallet_id__isnull=False)
    if as_of:
        qs = qs.filter(occurred_at__lte=as_of)
    rows = qs.values('wallet_id', 'direction').annotate(total=Sum('nominal'))
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


def _format_period_ranges(periods):
    """['2025-01', '2025-02', '2025-04', ...] (ascending) → 'Jan-Feb 2025, Apr 2025'.

    Consecutive months collapse into a single 'Mon-Mon YYYY' range; a gap
    (a paid month in between) starts a new range. A lone month has no dash.
    """
    if not periods:
        return ''

    def month_index(period):
        y, m = period.split('-')
        return int(y) * 12 + int(m)

    runs = []
    run = [periods[0]]
    for period in periods[1:]:
        if month_index(period) == month_index(run[-1]) + 1:
            run.append(period)
        else:
            runs.append(run)
            run = [period]
    runs.append(run)

    labels = []
    for run in runs:
        start = date(int(run[0][:4]), int(run[0][5:7]), 1)
        if len(run) == 1:
            labels.append(start.strftime('%b %Y'))
        else:
            end = date(int(run[-1][:4]), int(run[-1][5:7]), 1)
            if start.year == end.year:
                labels.append(f'{start.strftime("%b")}-{end.strftime("%b %Y")}')
            else:
                labels.append(f'{start.strftime("%b %Y")}-{end.strftime("%b %Y")}')
    return ', '.join(labels)


def resident_outstanding(users_qs, today=None):
    """
    Per-resident outstanding routine dues, from each user's earliest ROUTINE
    tariff up through the current month (inclusive), across all years.

    Returns [{
        'user', 'name', 'home_number',
        'fund_totals': [{'fund', 'total', 'total_display', 'periods_display'}],
        'total', 'total_display',
    }] — only residents with total > 0, sorted by total descending.
    """
    today = today or timezone.localdate()

    funds = list(Fund.objects.filter(kind=Fund.Kind.ROUTINE).order_by('name'))
    if not funds:
        return [], []

    earliest = Tariff.objects.filter(fund__kind=Fund.Kind.ROUTINE).order_by('start_from').values_list('start_from', flat=True).first()
    if earliest is None:
        return [], funds

    zero = Decimal('0')
    by_user = {user.id: {'user': user, 'fund_totals': {fund.id: {'total': zero, 'periods': []} for fund in funds}} for user in users_qs}

    for year in range(earliest.year, today.year + 1):
        last_month = today.month if year == today.year else 12
        months = [date(year, m, 1) for m in range(1, last_month + 1)]

        get_tariff = year_tariff_map(year)
        paid = year_paid_map(year)
        notes = year_note_map(year)

        for user_id in by_user:
            for fund in funds:
                for month_date in months:
                    expected = get_tariff(user_id, fund.id, month_date)
                    if expected is None:
                        continue
                    period = month_date.strftime('%Y-%m')
                    if (user_id, fund.id, period) in notes:
                        continue  # a DueNote marks this period as specially handled — not counted as outstanding
                    data = paid.get((user_id, fund.id, period))
                    total_paid = data['total'] if data else zero
                    outstanding = expected - total_paid
                    if outstanding <= zero:
                        continue
                    bucket = by_user[user_id]['fund_totals'][fund.id]
                    bucket['total'] += outstanding
                    bucket['periods'].append(period)

    rows = []
    for entry in by_user.values():
        user = entry['user']
        total = sum((b['total'] for b in entry['fund_totals'].values()), zero)
        if total <= zero:
            continue

        fund_totals = []
        for fund in funds:
            bucket = entry['fund_totals'][fund.id]
            if bucket['total'] <= zero:
                continue
            fund_totals.append({
                'fund': fund,
                'total': bucket['total'],
                'total_display': fmt_rupiah(bucket['total']),
                'periods_display': _format_period_ranges(bucket['periods']),
            })

        prop = getattr(user, 'properties', None)
        rows.append({
            'user': user,
            'name': user.get_full_name() or user.username,
            'home_number': (getattr(prop, 'home_number', '') or '') if prop is not None else '',
            'fund_totals': fund_totals,
            'total': total,
            'total_display': fmt_rupiah(total),
        })

    rows.sort(key=lambda r: r['total'], reverse=True)
    return rows, funds


def dot_status(amount, expected):
    if expected is None:
        return 'na'
    if amount >= expected:
        return 'paid'
    if amount > 0:
        return 'partial'
    return 'unpaid'


def cmp_status(actual, reference):
    """Compare actual vs reference → Kurang / Pas / Lebih. None when no reference."""
    if reference is None:
        return None
    if actual < reference:
        return {'code': 'kurang', 'label': 'Kurang'}
    if actual > reference:
        return {'code': 'lebih', 'label': 'Lebih'}
    return {'code': 'pas', 'label': 'Pas'}
