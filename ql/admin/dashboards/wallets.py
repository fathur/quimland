from decimal import Decimal

from django.contrib import admin
from django.shortcuts import render

from .data import parse_as_of_dt, wallet_money_map
from ql.models import Wallet
from ql.utils import fmt_rupiah


def wallet_dashboard_view(request):
    as_of       = parse_as_of_dt(request.GET.get('as_of', ''))
    as_of_input = as_of.strftime('%Y-%m-%dT%H:%M:%S') if as_of else ''

    money = wallet_money_map(as_of=as_of)
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
        'as_of_input': as_of_input,
        'as_of_label': as_of.strftime('%d %b %Y %H:%M:%S') if as_of else None,
    }
    return render(request, 'admin/wallet_dashboard.html', context)
