from decimal import Decimal

from django.contrib import admin
from django.shortcuts import render

from .data import fund_money_map, parse_as_of_dt
from ql.models import Fund
from ql.utils import fmt_rupiah


def funds_dashboard_view(request):
    as_of       = parse_as_of_dt(request.GET.get('as_of', ''))
    as_of_input = as_of.strftime('%Y-%m-%dT%H:%M:%S') if as_of else ''

    money = fund_money_map(as_of=as_of)
    zero  = Decimal('0')

    funds = list(Fund.objects.select_related('parent').order_by('-status', 'name'))

    def rollup(fund, key):
        """Own collected/spent plus every descendant's (child funds share the parent
        pool), found via the nested-set lft/rght range rather than walking parent/child
        links."""
        return sum(
            (
                money.get(f.id, {key: zero})[key]
                for f in funds
                if f.tree_id == fund.tree_id and fund.lft <= f.lft <= fund.rght
            ),
            zero,
        )

    total_balance = zero
    groups = {}
    for fund in funds:
        m = money.get(fund.id, {'collected': zero, 'spent': zero, 'balance': zero})
        total_balance += m['balance']

        is_child          = fund.parent_id is not None
        rolled_collected  = rollup(fund, 'collected')
        rolled_spent      = rollup(fund, 'spent')

        card = {
            'fund': fund,
            'is_open': fund.status == Fund.Status.OPEN,
            'is_earmarked': fund.kind == Fund.Kind.EARMARKED,
            'is_child': is_child,
            'collected_display': fmt_rupiah(rolled_collected),
            'spent_display': fmt_rupiah(rolled_spent),
            'target_display': fmt_rupiah(fund.target_amount) if fund.target_amount else None,
            'progress_pct': None,
        }
        if is_child:
            # A child isn't ring-fenced, so it has no balance of its own — the
            # shared pool's balance lives at the parent. Surface spent instead.
            card['balance_display']  = fmt_rupiah(rolled_spent)
            card['balance_negative'] = False
        else:
            balance = rolled_collected - rolled_spent
            card['balance_display']  = fmt_rupiah(balance)
            card['balance_negative'] = balance < 0
        if not is_child and fund.kind == Fund.Kind.EARMARKED and fund.target_amount:
            card['progress_pct'] = int(min(rolled_collected / fund.target_amount, 1) * 100)

        groups.setdefault(fund.kind, []).append(card)

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
        'as_of_input': as_of_input,
        'as_of_label': as_of.strftime('%d %b %Y %H:%M:%S') if as_of else None,
    }
    return render(request, 'admin/funds_dashboard.html', context)
