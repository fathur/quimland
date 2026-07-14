from django import template
from ql.utils import fmt_rupiah as _fmt_rupiah

register = template.Library()


@register.filter
def rupiah(value):
    if value is None:
        return '—'
    return _fmt_rupiah(value)
