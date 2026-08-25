"""
Management command: move_transaction_item
Moves one or more TransactionItem rows from their current Transaction to a
different one — for fixing items that were recorded against the wrong
transaction.

Usage:
  manage.py move_transaction_item <item_id> [<item_id> ...] --to <transaction_id> [--yes] [--force]

  - Any linked ItemRoutine moves for free — it's keyed off the item
    (transaction_item_id), not the transaction, so no extra handling needed.
  - item.direction is set on every item to mirror its transaction's own
    direction (see BaseTransactionAdmin.save_formset — it's not an
    exclusive "transfer leg override" despite the model's own docstring
    suggesting otherwise; TRANSFER isn't even a live Direction choice today).
    When the destination transaction has a different direction, this command
    updates item.direction to match, keeping that same invariant intact.
  - Refuses (unless --force) to move an item onto, or off of, a transfer or
    direct-expense leg (transaction.transfer_id / direct_expense_id set) —
    those are auto-managed pairs; editing their items directly bypasses
    invariants the admin already protects against (see
    BaseTransactionAdmin.has_change_permission).
  - Prompts for confirmation; pass --yes to skip (e.g. for scripting).

Examples:
  # Move item 42 onto transaction 108, with a confirmation prompt
  manage.py move_transaction_item 42 --to 108

  # Move several items at once, skipping the prompt
  manage.py move_transaction_item 42 43 44 --to 108 --yes
"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction
from django.db.models import Sum

from ql.fee.models import Transaction, TransactionItem
from ql.fee.services.utils import fmt_rupiah


def _nominal_mismatch(transaction):
    """(items_total, diff) for a Transaction — diff is transaction.nominal
    minus the sum of its items' nominal, same computation as
    BaseTransactionAdmin._check_nominal_mismatch()."""
    items_total = transaction.items.aggregate(s=Sum('nominal'))['s'] or Decimal('0')
    return items_total, transaction.nominal - items_total


class Command(BaseCommand):
    help = 'Move one or more transaction items to a different transaction.'

    def add_arguments(self, parser):
        parser.add_argument('item_ids', nargs='+', type=int, help='TransactionItem id(s) to move')
        parser.add_argument('--to', required=True, type=int, dest='to_id', help='Destination Transaction id')
        parser.add_argument('--yes', '-y', action='store_true', help='Skip the confirmation prompt')
        parser.add_argument(
            '--force', action='store_true',
            help='Allow moving an item onto/off a source or destination transaction '
                 'that is a transfer or direct-expense leg (normally blocked).',
        )

    def handle(self, *args, **options):
        item_ids = options['item_ids']
        force    = options['force']

        try:
            dest = Transaction.objects.select_related('user').get(pk=options['to_id'])
        except Transaction.DoesNotExist:
            raise CommandError(f'Destination transaction #{options["to_id"]} does not exist.')

        items = list(
            TransactionItem.objects
            .filter(pk__in=item_ids)
            .select_related('transaction', 'fund')
        )
        found_ids = {i.pk for i in items}
        missing = [i for i in item_ids if i not in found_ids]
        if missing:
            raise CommandError(f'Item id(s) not found: {", ".join(map(str, missing))}')

        already_there = [i for i in items if i.transaction_id == dest.pk]
        movable = [i for i in items if i.transaction_id != dest.pk]

        if self._dest_is_auto_managed(dest) and not force:
            raise CommandError(
                f'Transaction #{dest.pk} is a transfer/direct-expense leg — items on those are '
                'auto-managed by their parent record. Pass --force to override.'
            )

        blocked = []
        for item in movable:
            reason = self._blocked_reason(item, dest)
            if reason and not force:
                blocked.append((item, reason))
        if blocked:
            self.stdout.write(self.style.ERROR('Refusing to move (pass --force to override):'))
            for item, reason in blocked:
                self.stdout.write(f'  Item #{item.pk}: {reason}')
            raise CommandError(f'{len(blocked)} item(s) blocked, 0 moved.')

        if already_there:
            for item in already_there:
                self.stdout.write(self.style.WARNING(
                    f'Item #{item.pk} is already on transaction #{dest.pk} — skipping.'
                ))

        if not movable:
            self.stdout.write('Nothing to move.')
            return

        self._print_preview(movable, dest)

        if not options['yes']:
            answer = input(f'\nMove {len(movable)} item(s) to transaction #{dest.pk}? [y/N] ').strip().lower()
            if answer != 'y':
                self.stdout.write('Aborted.')
                return

        sources = {item.transaction for item in movable}
        with db_transaction.atomic():
            for item in movable:
                item.transaction = dest
                update_fields = ['transaction']
                # Keep the same invariant save_formset() maintains: direction
                # mirrors the item's (now new) transaction.
                if item.direction and item.direction != dest.direction:
                    item.direction = dest.direction
                    update_fields.append('direction')
                item.save(update_fields=update_fields)

        self.stdout.write(self.style.SUCCESS(f'\nMoved {len(movable)} item(s) to transaction #{dest.pk}.'))
        self._print_mismatch('Destination', dest)
        for src in sources:
            self._print_mismatch('Source', src)

    def _dest_is_auto_managed(self, transaction):
        return bool(transaction.transfer_id or transaction.direct_expense_id)

    def _blocked_reason(self, item, dest):
        src = item.transaction
        if src.transfer_id or src.direct_expense_id:
            return f'sits on transaction #{src.pk}, a transfer/direct-expense leg.'
        return None

    def _print_preview(self, items, dest):
        self.stdout.write(f'\nMoving {len(items)} item(s) to transaction #{dest.pk} ({dest.get_direction_display()}, {dest.user}):\n')
        for item in items:
            src = item.transaction
            line = (
                f'  #{item.pk}  {item.fund}  {fmt_rupiah(item.nominal)}  '
                f'from #{src.pk} ({src.get_direction_display()}) → #{dest.pk} ({dest.get_direction_display()})'
            )
            self.stdout.write(line)
            if item.direction and item.direction != dest.direction:
                self.stdout.write(self.style.WARNING(
                    f'    direction will be updated to match: {item.direction} → {dest.direction}'
                ))

    def _print_mismatch(self, label, transaction):
        items_total, diff = _nominal_mismatch(transaction)
        if diff == 0:
            self.stdout.write(
                f'{label} #{transaction.pk}: balanced ({fmt_rupiah(transaction.nominal)}).'
            )
        else:
            self.stdout.write(self.style.WARNING(
                f'{label} #{transaction.pk}: nominal {fmt_rupiah(transaction.nominal)} vs items '
                f'{fmt_rupiah(items_total)} — mismatch of {fmt_rupiah(abs(diff))}.'
            ))
