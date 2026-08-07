"""
Management command: migrate_storage_backend
Copies files for one model from one storage backend to another, then flips
each migrated row's `storage` column so future reads go to the new backend.
Reusable across every model with a per-row `storage` column (see
ql.fee.services.storage's DynamicStorage* fields): receipt, asset,
due_note_proof.

The file's path/name is preserved exactly — only which backend holds it
changes. The command refuses to continue if the destination would rename it
(e.g. a same-named object already sits there).

By default the source file is left in place after a successful copy (an
orphan, but a safety net) — pass --delete-source to remove it once you've
verified the migrated files are readable.

Usage:
  poetry run python manage.py migrate_storage_backend <model> [--to=r2]
      [--from=local] [--ids=1,2,3] [--dry-run] [--delete-source]

  - <model> is one of: receipt, asset, due_note_proof
  - --to defaults to 'r2'; --from defaults to "anything not already --to"
  - --ids limits the run to specific primary keys (comma-separated)
  - --dry-run reports what would move without touching files or the database

Examples:
  # See what would move, without doing anything
  manage.py migrate_storage_backend receipt --dry-run

  # Actually move every local receipt to R2, keeping local copies as backup
  manage.py migrate_storage_backend receipt

  # Move everything (receipts, assets, due note proofs) to R2
  manage.py migrate_storage_backend receipt
  manage.py migrate_storage_backend asset
  manage.py migrate_storage_backend due_note_proof

  # Once verified, free up local disk by deleting the now-migrated originals
  manage.py migrate_storage_backend receipt --delete-source

  # Move a specific handful of rows back to local
  manage.py migrate_storage_backend asset --to=local --ids=12,13,14
"""

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from ql.fee.models import Asset, DueNoteProof, Receipt
from ql.fee.services.storage import STORAGE_LOCAL, STORAGE_R2, storage_for_backend

# model key -> (Model, file field name)
_MODEL_MAP = {
    'receipt': (Receipt, 'image'),
    'asset': (Asset, 'file'),
    'due_note_proof': (DueNoteProof, 'image'),
}


class Command(BaseCommand):
    help = (
        "Copy a model's files from one storage backend to another and flip "
        "each row's `storage` column to match. Reusable across receipt/"
        "asset/due_note_proof — see this file's module docstring."
    )

    def add_arguments(self, parser):
        parser.add_argument('model', choices=sorted(_MODEL_MAP), help='Which table to migrate.')
        parser.add_argument(
            '--to', dest='to_backend', choices=[STORAGE_LOCAL, STORAGE_R2], default=STORAGE_R2,
            help='Target backend (default: r2).',
        )
        parser.add_argument(
            '--from', dest='from_backend', choices=[STORAGE_LOCAL, STORAGE_R2], default=None,
            help='Only migrate rows currently on this backend (default: any backend other than --to).',
        )
        parser.add_argument('--ids', help='Comma-separated primary keys to limit the run to.')
        parser.add_argument('--dry-run', action='store_true', help="Report what would move; don't touch files or the database.")
        parser.add_argument(
            '--delete-source', action='store_true',
            help='Delete the file from the source backend after a successful copy (default: keep it).',
        )

    def handle(self, *args, **options):
        model, field_name = _MODEL_MAP[options['model']]
        to_backend = options['to_backend']
        from_backend = options['from_backend']
        dry_run = options['dry_run']
        delete_source = options['delete_source']

        if from_backend == to_backend:
            raise CommandError('--from and --to are the same backend — nothing to do.')

        qs = model.objects.all()
        qs = qs.filter(storage=from_backend) if from_backend else qs.exclude(storage=to_backend)
        if options['ids']:
            try:
                ids = [int(x) for x in options['ids'].split(',') if x.strip()]
            except ValueError:
                raise CommandError('--ids must be a comma-separated list of integers.')
            qs = qs.filter(pk__in=ids)

        rows = list(qs)
        if not rows:
            self.stdout.write(self.style.SUCCESS('Nothing to migrate.'))
            return

        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(f'{prefix}Migrating {len(rows)} {options["model"]} row(s) to {to_backend}...')

        dest_storage = storage_for_backend(to_backend)
        moved = skipped = failed = 0

        for obj in rows:
            field_file = getattr(obj, field_name)
            if not field_file:
                self.stdout.write(f'  #{obj.pk}: no file — skipped')
                skipped += 1
                continue

            name = field_file.name
            source_storage = field_file.storage  # resolves from obj.storage, the CURRENT value

            if dry_run:
                self.stdout.write(f'  #{obj.pk}: {name} ({obj.storage} -> {to_backend})')
                continue

            if not source_storage.exists(name):
                self.stderr.write(self.style.ERROR(f'  #{obj.pk}: {name} not found on {obj.storage} — skipped'))
                failed += 1
                continue

            try:
                with source_storage.open(name, 'rb') as f:
                    data = f.read()
                saved_name = dest_storage.save(name, ContentFile(data))
                if saved_name != name:
                    # Destination already had a file at this exact path and
                    # Storage.get_available_name() renamed ours to avoid a
                    # collision — back out rather than silently changing the
                    # path (see this command's docstring).
                    dest_storage.delete(saved_name)
                    raise CommandError(
                        f'#{obj.pk}: destination already has a file named {name!r} '
                        f'(would have been saved as {saved_name!r}) — refusing to rename it.'
                    )
            except CommandError:
                raise
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f'  #{obj.pk}: {name} — copy failed: {exc}'))
                failed += 1
                continue

            model.objects.filter(pk=obj.pk).update(storage=to_backend)

            if delete_source:
                source_storage.delete(name)

            self.stdout.write(f'  #{obj.pk}: {name} -> {to_backend}' + (' (source deleted)' if delete_source else ''))
            moved += 1

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'{len(rows)} row(s) would be migrated.'))
            return
        summary = f'{moved} moved, {skipped} skipped, {failed} failed.'
        self.stdout.write(self.style.SUCCESS(summary) if not failed else self.style.WARNING(summary))
