from django.core.management.base import BaseCommand
from django.db.models import F, Q, Sum


class Command(BaseCommand):
    help = 'Find transactions where nominal does not match the sum of their items'

    def add_arguments(self, parser):
        parser.add_argument(
            '--direction',
            choices=['IN', 'OUT'],
            help='Limit check to a specific direction',
        )

    def handle(self, *args, **options):
        self._check_imbalanced(options['direction'])
        self.stdout.write('')
        self._check_contaminated_transfer_legs()

    def _check_imbalanced(self, direction=None):
        from ql.models import Transaction

        # Transfer legs intentionally have no items — exclude them from this check.
        qs = (
            Transaction.objects
            .filter(transfer__isnull=True)
            .annotate(total_items=Sum('items__nominal'))
        )
        if direction:
            qs = qs.filter(direction=direction)

        # NULL total_items means the transaction has no items at all — also imbalanced.
        mismatched = qs.filter(
            ~Q(nominal=F('total_items')) | Q(total_items__isnull=True)
        ).select_related('wallet', 'user').order_by('-occurred_at')

        count = mismatched.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS('All transactions are balanced.'))
            return
        self.stdout.write(self.style.ERROR(f'Found {count} imbalanced transaction(s):\n'))
        self._print_table(mismatched)
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(f'Total: {count} imbalanced transaction(s).'))

    def _check_contaminated_transfer_legs(self):
        from ql.models import Transaction

        contaminated = (
            Transaction.objects
            .filter(transfer__isnull=False)
            .annotate(total_items=Sum('items__nominal'))
            .filter(total_items__isnull=False)
            .select_related('wallet', 'user')
            .order_by('-occurred_at')
        )
        count = contaminated.count()
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
