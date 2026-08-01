import logging

from celery import shared_task
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string

from ql.admin.dashboards.data import resident_outstanding

logger = logging.getLogger('ql.tasks.access_control')

# Avoids visually ambiguous characters (0/O, 1/l/I) since these are handed to
# a resident to read/type, not just stored.
_PASSWORD_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'


def _generate_password():
    return get_random_string(10, allowed_chars=_PASSWORD_ALPHABET)


@shared_task
def sync_resident_admin_access(today=None):
    """Daily gate on admin login for residents: grant is_staff to those with
    no outstanding ROUTINE dues, revoke it from those who owe. Superusers are
    never touched. is_active is left alone — resident_outstanding()'s payment
    totals are keyed off it, so toggling it here would make a disabled
    resident's later payments invisible to their own next check.

    Doesn't touch groups/permissions — those vary by deployment (may not
    exist, or be split across several groups) and are out of scope here.

    Every resident cleared to log in (no outstanding dues) — whether newly
    granted here or already is_staff — gets a password generated if they
    don't have a usable one yet (accounts made via `add_user` default to
    none); is_staff=True alone wouldn't let them log in otherwise. New
    credentials are logged and returned in plaintext once, for handing to
    the resident — nothing else stores them.

    `today` overrides the as-of date; only meant for tests, production runs
    use the real current date.
    """
    residents = User.objects.filter(properties__isnull=False, is_superuser=False).select_related('properties')
    rows, _funds = resident_outstanding(residents, today=today)
    outstanding_ids = {row['user'].id for row in rows}

    to_disable = residents.filter(id__in=outstanding_ids, is_staff=True)
    disabled_count = to_disable.update(is_staff=False)

    # Fetched (not bulk-updated) because passwordless accounts among them
    # need a per-row set_password(), not just a flipped column.
    cleared = list(residents.exclude(id__in=outstanding_ids))
    new_credentials = []
    enabled_count = 0
    for user in cleared:
        changed = False
        if not user.is_staff:
            user.is_staff = True
            enabled_count += 1
            changed = True
        if not user.has_usable_password():
            password = _generate_password()
            user.set_password(password)
            new_credentials.append({'username': user.username, 'password': password})
            changed = True
        if changed:
            user.save()

    for cred in new_credentials:
        logger.info('sync_resident_admin_access: new password for %s: %s', cred['username'], cred['password'])

    logger.info(
        'sync_resident_admin_access: disabled=%d enabled=%d outstanding=%d passwords_created=%d',
        disabled_count, enabled_count, len(outstanding_ids), len(new_credentials),
    )
    return {'disabled': disabled_count, 'enabled': enabled_count, 'new_credentials': new_credentials}
