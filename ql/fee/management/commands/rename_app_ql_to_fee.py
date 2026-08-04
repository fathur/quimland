from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    """
    One-time fixup for the ql -> ql.fee app rename.

    The 'ql' Django app (app_label='ql') was moved to ql/fee/ and its
    app_label changed to 'fee'. Model code, migration files, and permission
    checks were all updated to match — but an EXISTING database still has
    rows keyed to the old app_label 'ql' in django_content_type and
    django_migrations, plus (if django_celery_beat has already seeded its
    schedule) a periodic task pointing at the old dotted task path.

    This command updates those rows IN PLACE (same primary keys), so every
    existing foreign key — auth_permission.content_type_id,
    auth_user_user_permissions, auth_group_permissions, django_admin_log —
    keeps pointing at the same row and nothing is lost. It must be run
    ONCE, right after deploying this code change and BEFORE running
    `migrate` (otherwise Django will find no migration history for the
    'fee' app and try to re-run 0001_initial from scratch).

    Safe to run more than once — every statement is scoped to rows still
    tagged 'ql', so a second run is a no-op.
    """

    help = 'One-time fixup: relabel existing ql app_label rows to fee (content types, migrations, celery beat).'

    OLD_TASK_PATH = 'ql.tasks.access_control.sync_resident_admin_access'
    NEW_TASK_PATH = 'ql.fee.tasks.access_control.sync_resident_admin_access'

    def handle(self, *args, **options):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE django_content_type SET app_label = 'fee' WHERE app_label = 'ql'"
                )
                content_types_updated = cursor.rowcount

                cursor.execute(
                    "UPDATE django_migrations SET app = 'fee' WHERE app = 'ql'"
                )
                migrations_updated = cursor.rowcount

                periodic_tasks_updated = 0
                if 'django_celery_beat_periodictask' in connection.introspection.table_names():
                    cursor.execute(
                        "UPDATE django_celery_beat_periodictask SET task = %s WHERE task = %s",
                        [self.NEW_TASK_PATH, self.OLD_TASK_PATH],
                    )
                    periodic_tasks_updated = cursor.rowcount

        self.stdout.write(self.style.SUCCESS(
            f'content types relabeled: {content_types_updated}, '
            f'migrations relabeled: {migrations_updated}, '
            f'periodic tasks repointed: {periodic_tasks_updated}'
        ))
        if content_types_updated == 0 and migrations_updated == 0:
            self.stdout.write(self.style.WARNING(
                "Nothing to do — either this has already been run, or the database "
                "never had app_label='ql' rows (fresh database)."
            ))
