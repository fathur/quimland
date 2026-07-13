from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.models import User
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from .data import cmp_status, parse_as_of_date
from ql.models import CashEntry, Fund, FundDue
from ql.utils import fmt_rupiah


def earmarked_dashboard_view(request):
    funds = list(
        Fund.objects
        .filter(kind=Fund.Kind.EARMARKED)
        .order_by('-status', 'name')
    )

    selected_id = request.GET.get('fund')
    selected = None
    if selected_id:
        selected = next((f for f in funds if str(f.id) == selected_id), None)
    if selected is None and funds:
        selected = funds[0]

    as_of = parse_as_of_date(request.GET.get('as_of'))

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

    entries = CashEntry.objects.filter(fund=selected)
    if as_of:
        entries = entries.filter(occurred_at__date__lte=as_of)

    zero = Decimal('0')
    collected = entries.filter(direction=CashEntry.Direction.IN).aggregate(s=Sum('amount'))['s'] or zero
    spent     = entries.filter(direction=CashEntry.Direction.OUT).aggregate(s=Sum('amount'))['s'] or zero
    balance   = collected - spent

    total_expected = FundDue.objects.filter(fund=selected).aggregate(s=Sum('expected_amount'))['s'] or zero
    target     = selected.target_amount
    has_dues   = FundDue.objects.filter(fund=selected).exists()

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
    users    = {u.id: u for u in User.objects.filter(id__in=user_ids)}

    counts = {'kurang': 0, 'pas': 0, 'lebih': 0, 'sukarela': 0}
    people = []
    for uid in user_ids:
        user      = users.get(uid)
        expected  = expected_map.get(uid, zero)
        paid      = paid_map.get(uid, zero)
        diff      = paid - expected
        voluntary = uid not in expected_map
        status    = cmp_status(paid, expected)

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
        'status_vs_target': cmp_status(collected, target),
        'status_vs_expected': cmp_status(collected, total_expected) if has_dues else None,
        'target_pct': int(min(collected / target, 1) * 100) if target else None,
        'has_dues': has_dues,
        'people': people,
        'counts': counts,
        'total_people': len(people),
    })
    return render(request, 'admin/earmarked_dashboard.html', context)
