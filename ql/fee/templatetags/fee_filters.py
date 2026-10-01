from django import template
from ql.fee.services.utils import fmt_rupiah as _fmt_rupiah

register = template.Library()


@register.filter
def rupiah(value):
    if value is None:
        return '—'
    return _fmt_rupiah(value)


@register.filter
def rp(value):
    """Compact Rupiah for dense tables: 'Rp 1.410.000' (whole rupiah, no ',00')."""
    if value is None:
        return '—'
    return 'Rp ' + f'{value:,.0f}'.replace(',', '.')
