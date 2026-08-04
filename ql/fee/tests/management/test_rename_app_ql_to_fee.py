from io import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from django_celery_beat.models import IntervalSchedule, PeriodicTask


class RenameAppQlToFeeTests(TestCase):
    """
    Covers ql/fee/management/commands/rename_app_ql_to_fee.py — the one-time
    fixup that relabels leftover app_label='ql' rows (from before the
    ql -> ql/fee app rename) to 'fee' in place, so existing foreign keys
    (permissions, admin log, periodic tasks) keep pointing at the same rows.
    """

    OLD_TASK_PATH = 'ql.tasks.access_control.sync_resident_admin_access'
    NEW_TASK_PATH = 'ql.fee.tasks.access_control.sync_resident_admin_access'

    def call(self):
        out = StringIO()
        call_command('rename_app_ql_to_fee', stdout=out)
        return out.getvalue()

    def test_relabels_content_type_in_place(self):
        ct = ContentType.objects.create(app_label='ql', model='fakemodelxyz')
        self.call()
        ct.refresh_from_db()
        self.assertEqual(ct.app_label, 'fee')

    def test_content_type_pk_unchanged_by_relabel(self):
        ct = ContentType.objects.create(app_label='ql', model='fakemodelxyz')
        pk = ct.pk
        self.call()
        ct.refresh_from_db()
        self.assertEqual(ct.pk, pk)

    def test_other_app_labels_left_untouched(self):
        ct = ContentType.objects.create(app_label='auth', model='fakemodelxyz')
        self.call()
        ct.refresh_from_db()
        self.assertEqual(ct.app_label, 'auth')

    def test_relabels_django_migrations_app(self):
        # Use a migration name that can't collide with the real, already-applied
        # fee.0001_initial row in the test database.
        fake_name = '0001_initial_rename_test_fake'
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO django_migrations (app, name, applied) "
                "VALUES ('ql', %s, %s)",
                [fake_name, timezone.now()],
            )
        self.call()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT app FROM django_migrations WHERE name = %s",
                [fake_name],
            )
            apps = [row[0] for row in cursor.fetchall()]
        self.assertEqual(apps, ['fee'])

    def test_repoints_periodic_task(self):
        schedule = IntervalSchedule.objects.create(every=1, period=IntervalSchedule.DAYS)
        task = PeriodicTask.objects.create(
            name='sync-resident-admin-access-daily-test',
            task=self.OLD_TASK_PATH,
            interval=schedule,
        )
        self.call()
        task.refresh_from_db()
        self.assertEqual(task.task, self.NEW_TASK_PATH)

    def test_leaves_unrelated_periodic_task_untouched(self):
        schedule = IntervalSchedule.objects.create(every=1, period=IntervalSchedule.DAYS)
        task = PeriodicTask.objects.create(
            name='some-other-task',
            task='ql.fee.tasks.access_control.some_other_task',
            interval=schedule,
        )
        self.call()
        task.refresh_from_db()
        self.assertEqual(task.task, 'ql.fee.tasks.access_control.some_other_task')

    def test_idempotent_second_run_touches_nothing(self):
        ContentType.objects.create(app_label='ql', model='fakemodelxyz')
        self.call()
        second_output = self.call()
        self.assertIn('content types relabeled: 0', second_output)
        self.assertIn('migrations relabeled: 0', second_output)

    def test_reports_counts_in_output(self):
        ContentType.objects.create(app_label='ql', model='fakemodelxyz')
        ContentType.objects.create(app_label='ql', model='fakemodelabc')
        output = self.call()
        self.assertIn('content types relabeled: 2', output)
