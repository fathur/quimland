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
from ql.models.tariff import Tariff

SENTINEL = '[migrated_from_batch]'





class Command(BaseCommand):
    help = 'Migrate PaymentBatch/Payment rows into Transaction/TransactionItem/ItemRoutine/Receipt.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be done without writing anything.',
        )

    def handle(self, *_, **options):
        tariffs = Tariff.objects.filter(fund__isnull=True)

        ipl = Fund.objects.filter(kind=Fund.Kind.ROUTINE, name="IPL").first()
        garbage = Fund.objects.filter(kind=Fund.Kind.ROUTINE, name="Sampah").first()

        for tariff in tariffs:
           tariff.fund = ipl if tariff.kind == Tariff.Kind.MONTHLY else garbage
           tariff.save()
