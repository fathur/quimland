from decimal import Decimal

from django.conf import settings as dj_settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db import transaction as db_transaction
from django.utils import timezone

from .base import TimestampMixin


class DirectExpense(TimestampMixin):
    """A resident pays for something directly out of pocket — no money ever
    passes through a tracked wallet. Modeled as two IN/OUT Transaction legs
    against one dedicated wallet (settings.DIRECT_EXPENSE_WALLET_ID) that
    always nets to zero: the IN leg credits the resident's contribution, the
    OUT leg (receipt attached) debits the same amount as the real purchase —
    both legs carry the same `user` (the resident, who is also the one
    responsible for the purchase). Items are entered once, on the OUT leg's
    shape (fund/name/price/quantity), and mirrored 1:1 by (fund, nominal)
    onto the IN leg — see sync_legs() — so per-fund collected/spent totals
    both move correctly and the two legs' nominal (hence the shared wallet's
    balance) always match.
    """

    user = models.ForeignKey(
        dj_settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='direct_expenses',
        help_text='Resident who paid directly — becomes the user on both the IN and OUT leg.',
    )
    occurred_at = models.DateTimeField()
    note        = models.TextField(blank=True, default='')
    creator     = models.ForeignKey(
        dj_settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='created_direct_expenses',
    )
    # Cached sum of the expense leg's items — not directly editable. Kept in
    # sync (create, item update, item delete) by sync_legs(), which is also
    # what pushes this same value onto both legs' Transaction.nominal.
    nominal = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal('0'))

    # CASCADE: a Direct Expense and its two legs are one atomic unit, same
    # reasoning as WalletTransfer.out_transaction/in_transaction.
    income_transaction = models.OneToOneField(
        'Transaction', on_delete=models.CASCADE, editable=False, related_name='+',
    )
    expense_transaction = models.OneToOneField(
        'Transaction', on_delete=models.CASCADE, editable=False, related_name='+',
    )

    class Meta:
        db_table = 'direct_expenses'

    def __str__(self):
        return f'Direct Expense #{self.pk} | {self.user}'

    @staticmethod
    def wallet():
        wallet_id = getattr(dj_settings, 'DIRECT_EXPENSE_WALLET_ID', None)
        if not wallet_id:
            raise ImproperlyConfigured(
                'DIRECT_EXPENSE_WALLET_ID is not set — create the direct-expense '
                'wallet in the admin and point the env var at its id.'
            )
        from .wallet import Wallet
        return Wallet.objects.get(pk=wallet_id)

    def save(self, *args, **kwargs):
        from .transaction import Transaction

        creating = self.pk is None
        wallet = self.wallet()
        if creating:
            with db_transaction.atomic():
                self.income_transaction = Transaction.objects.create(
                    direction=Transaction.Direction.IN, wallet=wallet,
                    nominal=Decimal('0'), occurred_at=self.occurred_at,
                    user=self.user, creator=self.creator,
                )
                self.expense_transaction = Transaction.objects.create(
                    direction=Transaction.Direction.OUT, wallet=wallet,
                    nominal=Decimal('0'), occurred_at=self.occurred_at,
                    user=self.user, creator=self.creator,
                )
                super().save(*args, **kwargs)
                # Tag both legs now that this Direct Expense has a pk — mirrors
                # WalletTransfer's post-save tagging (see its save() comment).
                Transaction.objects.filter(
                    pk__in=[self.income_transaction_id, self.expense_transaction_id]
                ).update(direct_expense=self)
                self.income_transaction.direct_expense = self
                self.expense_transaction.direct_expense = self
        else:
            with db_transaction.atomic():
                super().save(*args, **kwargs)

                in_tx = self.income_transaction
                in_tx.occurred_at = self.occurred_at
                in_tx.wallet      = wallet
                in_tx.user        = self.user
                in_tx.save()

                out_tx = self.expense_transaction
                out_tx.occurred_at = self.occurred_at
                out_tx.wallet      = wallet
                out_tx.user        = self.user
                out_tx.save()

    def sync_legs(self):
        """Rebuild the income leg's items from the expense leg's items (same
        fund + nominal, no name/price/quantity — those are OUT-only
        descriptive fields), recompute the item total, and push it to
        self.nominal AND both legs' Transaction.nominal (keeping the shared
        wallet's balance at zero) — plus stamp both notes with the pairing.
        Call after the expense-side items have been created, updated, or
        deleted (see DirectExpenseAdmin.save_formset) — including on the
        very first save, so nominal is never left at its 0 default."""
        from .transaction import Transaction
        from .transaction_item import TransactionItem

        with db_transaction.atomic():
            self.income_transaction.items.all().delete()
            total = Decimal('0')
            for item in self.expense_transaction.items.all():
                TransactionItem.objects.create(
                    transaction=self.income_transaction,
                    fund=item.fund,
                    nominal=item.nominal,
                )
                total += item.nominal

            tag = (
                f'Direct expense — resident paid directly; '
                f'Income #{self.income_transaction_id} ↔ Expense #{self.expense_transaction_id}.'
            )
            note = f'{self.note}\n\n[{tag}]' if self.note else f'[{tag}]'

            Transaction.objects.filter(pk=self.income_transaction_id).update(nominal=total, note=note)
            Transaction.objects.filter(pk=self.expense_transaction_id).update(nominal=total, note=note)
            DirectExpense.objects.filter(pk=self.pk).update(nominal=total)
            self.nominal = total

    def delete(self, using=None, keep_parents=False):
        # Bulk .update() (not leg.delete()) deliberately bypasses
        # Transaction.delete(), which would otherwise recurse back into this
        # method via self.direct_expense.delete() — mirrors WalletTransfer.delete().
        with db_transaction.atomic():
            from .transaction import Transaction
            from .transaction_item import TransactionItem

            now = timezone.now()
            leg_ids = [self.income_transaction_id, self.expense_transaction_id]
            TransactionItem.objects.filter(transaction_id__in=leg_ids).update(deleted_at=now)
            Transaction.objects.filter(pk__in=leg_ids).update(deleted_at=now)
            DirectExpense.objects.filter(pk=self.pk).update(deleted_at=now)
            self.deleted_at = now

    def force_delete(self, using=None, keep_parents=False):
        with db_transaction.atomic():
            from .transaction import Transaction
            from .transaction_item import TransactionItem

            leg_ids = [self.income_transaction_id, self.expense_transaction_id]
            TransactionItem.objects.with_deleted().filter(transaction_id__in=leg_ids).force_delete()
            Transaction.objects.with_deleted().filter(pk__in=leg_ids).force_delete()
            super().force_delete(using=using, keep_parents=keep_parents)

    def restore(self):
        with db_transaction.atomic():
            from .transaction import Transaction
            from .transaction_item import TransactionItem

            leg_ids = [self.income_transaction_id, self.expense_transaction_id]
            # Only restore items that were deleted *by this same delete() call*
            # (same deleted_at) — unlike WalletTransfer legs, DirectExpense legs
            # do carry items, and an item can be independently soft-deleted
            # earlier (e.g. removed via the formset on an edit). A blanket
            # with_deleted().restore() would incorrectly resurrect those too.
            TransactionItem.objects.with_deleted().filter(
                transaction_id__in=leg_ids, deleted_at=self.deleted_at,
            ).restore()
            Transaction.objects.with_deleted().filter(pk__in=leg_ids).restore()
            super().restore()
