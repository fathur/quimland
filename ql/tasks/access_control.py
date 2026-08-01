import logging

from celery import shared_task
from django.contrib.auth.models import User

from ql.admin.dashboards.data import resident_outstanding

logger = logging.getLogger('ql.tasks.access_control')


@shared_task
def sync_resident_admin_access(today=None):
    """Daily gate on admin login for residents: grant is_staff to those with
    no outstanding ROUTINE dues, revoke it from those who owe. Superusers are
    never touched. is_active is left alone — resident_outstanding()'s payment
    totals are keyed off it, so toggling it here would make a disabled
    resident's later payments invisible to their own next check.

    Doesn't touch groups/permissions — those vary by deployment (may not
    exist, or be split across several groups) and are out of scope here.

    `today` overrides the as-of date; only meant for tests, production runs
    use the real current date.
    """
    residents = User.objects.filter(properties__isnull=False, is_superuser=False).select_related('properties')
    rows, _funds = resident_outstanding(residents, today=today)
    outstanding_ids = {row['user'].id for row in rows}

    to_disable = residents.filter(id__in=outstanding_ids, is_staff=True)
    disabled_count = to_disable.update(is_staff=False)

    to_enable = residents.exclude(id__in=outstanding_ids).filter(is_staff=False)
    enabled_count = to_enable.update(is_staff=True)

    logger.info(
        'sync_resident_admin_access: disabled=%d enabled=%d outstanding=%d',
        disabled_count, enabled_count, len(outstanding_ids),
    )
    return {'disabled': disabled_count, 'enabled': enabled_count}
