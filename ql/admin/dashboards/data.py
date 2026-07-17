from datetime import date, datetime
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from ql.models import DueNote, Fund, ItemRoutine, Tariff, Transaction, TransactionItem


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
