from django.core.management.base import BaseCommand

from ql.admin.dashboards.data import imbalance_summary


class Command(BaseCommand):
    help = 'Find transactions where nominal does not match the sum of their items'

    def add_arguments(self, parser):
        parser.add_argument(
            '--direction',
            choices=['IN', 'OUT'],
            help='Limit check to a specific direction',
        )

    def handle(self, *args, **options):
        data = imbalance_summary(direction=options['direction'])
        self._check_imbalanced(data['imbalance_mismatched'])
        self.stdout.write('')
        self._check_contaminated_transfer_legs(data['imbalance_contaminated'])

    def _check_imbalanced(self, mismatched):
        count = len(mismatched)
        if count == 0:
            self.stdout.write(self.style.SUCCESS('All transactions are balanced.'))
            return
        self.stdout.write(self.style.ERROR(f'Found {count} imbalanced transaction(s):\n'))
        self._print_table(mismatched)
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(f'Total: {count} imbalanced transaction(s).'))

    def _check_contaminated_transfer_legs(self, contaminated):
        count = len(contaminated)
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No transfer legs with items found.'))
            return
        self.stdout.write(self.style.ERROR(
            f'Found {count} transfer leg(s) with items attached (data integrity issue):\n'
        ))
        self._print_table(contaminated)

    def _print_table(self, qs):
        self.stdout.write(
            f"{'ID':<8} {'Date':<12} {'Dir':<4} {'Transfer':<10} {'Wallet':<20} {'User':<20} {'Nominal':>14} {'Sum Items':>14} {'Diff':>14}"
        )
        self.stdout.write('-' * 122)
        for tx in qs:
            nominal   = tx.nominal
            total     = tx.total_items
            diff      = (nominal - total) if total is not None else nominal
            wallet    = str(tx.wallet)[:18] if tx.wallet else '—'
            user      = (tx.user.get_full_name() or tx.user.username)[:18] if tx.user else '—'
            date      = tx.occurred_at.strftime('%Y-%m-%d') if tx.occurred_at else '—'
            transfer  = f'#{tx.transfer_id}' if tx.transfer_id else '—'
            total_str = f'{total:,.0f}' if total is not None else 'NO ITEMS'
            diff_str  = f'{diff:+,.0f}' if total is not None else f'{nominal:+,.0f}'
            self.stdout.write(
                f'{tx.id:<8} {date:<12} {tx.direction:<4} {transfer:<10} {wallet:<20} {user:<20} '
                f'{nominal:>14,.0f} {total_str:>14} {diff_str:>14}'
            )
