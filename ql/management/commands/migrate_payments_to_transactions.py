"""
Management command: migrate_payments_to_transactions

Copies production data from the old PaymentBatch/Payment tables into the
new Transaction/TransactionItem/ItemRoutine/Receipt tables.

Rules:
  - Every PaymentBatch with a receipt image gets a Receipt row created and
    linked to its Transaction (if migrated) or left unlinked (if not yet).
  - Only batches that have at least one Payment are migrated into Transaction.
    Batches without Payment rows (incomplete legacy data) are skipped for the
    Transaction part — only their receipts are migrated.
  - Each PaymentBatch becomes one Transaction (direction=IN).
  - Each Payment becomes one TransactionItem + one ItemRoutine.
  - Payment.kind=MONTHLY  → TransactionItem.fund = Fund(kind=GENERAL)
  - Payment.kind=GARBAGE  → TransactionItem.fund = Fund(kind=GARBAGE)
  - Transaction.nominal uses batch.nominal when > 0, otherwise falls back
    to SUM(payment.nominal) for older batches that predate the nominal field.
  - Idempotent: already-migrated batches are detected via a sentinel in
    Transaction.note and skipped on re-runs.

Usage:
    python manage.py migrate_payments_to_transactions [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction

from ql.models import (
    Fund, ItemRoutine, PaymentBatch, Receipt,
    Transaction, TransactionItem,
)

SENTINEL = '[migrated_from_batch]'


def _migrate_receipt(batch):
    """
    Create a Receipt row pointing at batch's existing file, or return the
    existing one if already migrated (idempotent by image path).
    The file is NOT copied or recompressed — we just reference the same path.
    Returns the Receipt instance.
    """
    existing = Receipt.objects.filter(image=batch.receipt.name).first()
    if existing:
        return existing

    receipt = Receipt(
        user_id=batch.user_id,
        receipt_storage=batch.receipt_storage,
    )
    # Assign the existing path directly to bypass the upload/compression logic.
    receipt.image.name = batch.receipt.name
    receipt.save()
    return receipt


class Command(BaseCommand):
    help = 'Migrate PaymentBatch/Payment rows into Transaction/TransactionItem/ItemRoutine/Receipt.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be done without writing anything.',
        )

    def handle(self, *_, **options):
        dry_run = options['dry_run']

        try:
            general_fund = Fund.objects.get(kind=Fund.Kind.GENERAL)
            garbage_fund = Fund.objects.get(kind=Fund.Kind.GARBAGE)
        except Fund.DoesNotExist as e:
            self.stderr.write(self.style.ERROR(f'Required fund missing: {e}'))
            return

        fund_map = {
            'MONTHLY': general_fund,
            'GARBAGE': garbage_fund,
        }

        batches = (
            PaymentBatch.objects
            .prefetch_related('payments')
            .order_by('paid_at', 'pk')
        )

        migrated = receipt_only = skipped_already_done = 0

        for batch in batches:
            breakpoint()
            payments = list(batch.payments.all())
            has_receipt = bool(batch.receipt)

            # Idempotency: skip if a Transaction already carries this batch's sentinel.
            already = Transaction.objects.filter(
                note=f'{SENTINEL}#{batch.pk}'
            ).exists()
            if already:
                self.stdout.write(f'  SKIP  batch #{batch.pk} — already migrated')
                skipped_already_done += 1
                continue

            # if not payments:
            #     if has_receipt:
            #         self.stdout.write(
            #             f'  {"DRY " if dry_run else ""}RECEIPT-ONLY  '
            #             f'batch #{batch.pk} ({batch.user}) — no payments, migrating receipt only'
            #         )
            #         self.stdout.write(f'    receipt: {batch.receipt.name}')
            #         if not dry_run:
            #             with db_transaction.atomic():
            #                 _migrate_receipt(batch)
            #         receipt_only += 1
            #     else:
            #         self.stdout.write(
            #             f'  SKIP  batch #{batch.pk} ({batch.user}) — no payments, no receipt'
            #         )
            #     continue

            nominal = batch.nominal if batch.nominal > 0 else sum(p.nominal for p in payments)
            note = f'{batch.note}\n{SENTINEL}#{batch.pk}'.strip()

            self.stdout.write(
                f'  {"DRY " if dry_run else ""}MIGRATE  batch #{batch.pk} '
                f'({batch.user}, {batch.paid_at:%Y-%m-%d}, nominal={nominal:,}, '
                f'{len(payments)} payment(s), receipt={has_receipt})'
            )
            for p in payments:
                self.stdout.write(f'    → {p.kind} {p.period} {p.nominal:,}')

            if dry_run:
                migrated += 1
                continue

            with db_transaction.atomic():
                receipt_obj = _migrate_receipt(batch) if has_receipt else None

                trx = Transaction.objects.create(
                    direction=Transaction.Direction.IN,
                    nominal=nominal,
                    occurred_at=batch.paid_at,
                    user=batch.user,
                    creator=batch.creator,
                    receipt=receipt_obj,
                    note=note,
                )

                for payment in payments:
                    item = TransactionItem.objects.create(
                        transaction=trx,
                        fund=fund_map[payment.kind],
                        direction=None,
                        nominal=payment.nominal,
                    )
                    ItemRoutine.objects.create(
                        transaction_item=item,
                        period=payment.period,
                    )

            migrated += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done.  migrated={migrated}  '
            f'receipt_only={receipt_only}  '
            f'skipped_already_done={skipped_already_done}'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing was written.'))
            return

        self._backfill_receipt_ids()
        self._verify()

    def _backfill_receipt_ids(self):
        """
        For already-migrated Transactions that have receipt_id=NULL, check if
        their source PaymentBatch has a Receipt row and link it.
        """
        self.stdout.write('\nBackfilling Transaction.receipt_id for previously migrated rows...')
        updated = 0
        for batch in PaymentBatch.objects.exclude(receipt='').prefetch_related('payments'):
            if not batch.receipt:
                continue
            receipt_obj = Receipt.objects.filter(image=batch.receipt.name).first()
            if not receipt_obj:
                continue
            trx = Transaction.objects.filter(
                note__contains=f'{SENTINEL}#{batch.pk}',
                receipt__isnull=True,
            ).first()
            if trx:
                trx.receipt = receipt_obj
                trx.save(update_fields=['receipt'])
                self.stdout.write(f'  Linked trx #{trx.pk} → Receipt #{receipt_obj.pk}')
                updated += 1
        if not updated:
            self.stdout.write('  Nothing to backfill.')

    def _verify(self):
        self.stdout.write('\nVerifying Transaction.nominal == SUM(items)...')
        mismatches = []
        for trx in Transaction.objects.prefetch_related('items').all():
            item_sum = sum(i.nominal for i in trx.items.all())
            if item_sum and item_sum != trx.nominal:
                mismatches.append((trx.pk, trx.nominal, item_sum))

        if mismatches:
            self.stderr.write(self.style.ERROR('MISMATCHES found:'))
            for pk, trx_nom, s in mismatches:
                self.stderr.write(f'  trx #{pk}: trx.nominal={trx_nom}  items_sum={s}')
        else:
            self.stdout.write(self.style.SUCCESS('All transactions balance correctly.'))
