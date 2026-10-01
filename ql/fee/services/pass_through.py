"""Ledger for pass-through funds (money collected is handed over as-is, e.g.
garbage collector pay). Per routine period (YYYY-MM):

    collected(P) = Σ IN items of the fund tagged with ItemRoutine.period = P
    paid(P)      = Σ RoutinePayout.amount allocated to P
    remaining(P) = collected(P) − paid(P)

Late payments raise collected(P) of an earlier month, which is how a "rapel"
shows up as a remaining balance on a month that was already paid out once.
Periods after the current month are held (paid in advance, not yet payable).
"""

from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from ql.fee.models import ItemRoutine, RoutinePayout, Transaction, TransactionItem

ZERO = Decimal('0')


def period_of(day):
    return day.strftime('%Y-%m')


def _month_index(period):
    return int(period[:4]) * 12 + int(period[5:7]) - 1


def _period_from_index(index):
    return f'{index // 12:04d}-{index % 12 + 1:02d}'


def collected_by_period(fund):
    """{period: {'total': Decimal, 'payments': int}} of money collected for `fund`."""
    rows = (
        ItemRoutine.objects
        .filter(
            transaction_item__fund=fund,
            transaction_item__transaction__direction=Transaction.Direction.IN,
            transaction_item__deleted_at__isnull=True,
            transaction_item__transaction__deleted_at__isnull=True,
        )
        .values('period')
        .annotate(
            total=Sum('transaction_item__nominal'),
            payments=Count('transaction_item__transaction', distinct=True),
        )
    )
    return {r['period']: {'total': r['total'] or ZERO, 'payments': r['payments']} for r in rows}


def _active_payouts(fund):
    return RoutinePayout.objects.filter(
        transaction_item__fund=fund,
        transaction_item__deleted_at__isnull=True,
        transaction_item__transaction__deleted_at__isnull=True,
    )


def paid_by_period(fund):
    rows = _active_payouts(fund).values('period').annotate(total=Sum('amount'))
    return {r['period']: r['total'] or ZERO for r in rows}


def remaining_for_period(fund, period):
    collected = collected_by_period(fund).get(period, {'total': ZERO})['total']
    return collected - paid_by_period(fund).get(period, ZERO)


def payable_items(fund):
    """OUT items of `fund` that still have an amount not allocated to any period,
    newest first, each annotated with `.unallocated`."""
    allocated = Coalesce(
        Sum('payouts__amount', filter=Q(payouts__deleted_at__isnull=True)),
        Value(ZERO),
        output_field=DecimalField(max_digits=15, decimal_places=2),
    )
    return (
        TransactionItem.objects
        .filter(
            fund=fund,
            transaction__direction=Transaction.Direction.OUT,
            transaction__deleted_at__isnull=True,
        )
        .annotate(allocated=allocated)
        .annotate(unallocated=F('nominal') - F('allocated'))
        .filter(unallocated__gt=0)
        .select_related('transaction')
        .order_by('-transaction__occurred_at', '-id')
    )


def pass_through_ledger(fund, today=None):
    """Per-period ledger plus headline totals for `fund`.

    Returns {
        'rows': [{'period', 'month', 'collected', 'payments', 'paid', 'remaining',
                  'is_held', 'over_paid', 'payouts'}],  # ascending, no gaps
        'collected_total', 'paid_total',
        'due_now',   # Σ remaining of periods up to the current month
        'held',      # collected for months after the current one
    }
    """
    today = today or timezone.localdate()
    current = period_of(today)

    collected = collected_by_period(fund)
    paid = paid_by_period(fund)

    payouts_by_period = {}
    for payout in _active_payouts(fund).select_related('transaction_item__transaction'):
        payouts_by_period.setdefault(payout.period, []).append(payout)

    known = set(collected) | set(paid)
    rows = []
    if known:
        first, last = _month_index(min(known)), _month_index(max(known | {current}))
        for index in range(first, last + 1):
            period = _period_from_index(index)
            c = collected.get(period, {'total': ZERO, 'payments': 0})
            p = paid.get(period, ZERO)
            rows.append({
                'period': period,
                'month': date(int(period[:4]), int(period[5:7]), 1),
                'collected': c['total'],
                'payments': c['payments'],
                'paid': p,
                'remaining': c['total'] - p,
                'is_held': period > current,
                'over_paid': p > c['total'],
                'payouts': payouts_by_period.get(period, []),
            })

    due_rows = [r for r in rows if not r['is_held']]
    return {
        'rows': rows,
        'collected_total': sum((r['collected'] for r in due_rows), ZERO),
        'paid_total': sum((r['paid'] for r in rows), ZERO),
        'due_now': sum((max(r['remaining'], ZERO) for r in due_rows), ZERO),
        'held': sum((r['collected'] - r['paid'] for r in rows if r['is_held']), ZERO),
    }
