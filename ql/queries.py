"""
RT Finance report queries — one function per report.

All functions accept an optional `as_of` date (defaults to today).
`period` arguments are strings in YYYY-MM format.
`fund_id` for report 3 is the PK of the target EARMARKED Fund.

Each function returns a QuerySet or list of dicts suitable for JSON
serialisation or template rendering.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.db import connection
from django.db.models import Q, Sum, OuterRef, Subquery, DecimalField, Value
from django.db.models.functions import Coalesce

from .models import Fund, FundDue, Payment, PaymentBatch, Payout, SalaryRate, CashEntry


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _today() -> datetime.date:
    return datetime.date.today()


def _period_to_date(period: str) -> datetime.date:
    """'YYYY-MM' → first day of that month."""
    return datetime.date.fromisoformat(period + '-01')


def _garbage_payout_date(period: str, paid_at: datetime.datetime | datetime.date) -> datetime.date:
    """
    Sanitation timing rule:
        eligible    = max(paid_at.date(), day-10-of-period-month)
        payout_date = the next of [10, 25] that is >= eligible
    """
    paid_date    = paid_at.date() if hasattr(paid_at, 'date') else paid_at
    period_day10 = _period_to_date(period).replace(day=10)
    eligible     = max(paid_date, period_day10)

    month_start = eligible.replace(day=1)
    d10 = month_start.replace(day=10)
    d25 = month_start.replace(day=25)

    if eligible <= d10:
        return d10
    if eligible <= d25:
        return d25
    # roll to day-10 of next month
    if month_start.month == 12:
        return datetime.date(month_start.year + 1, 1, 10)
    return datetime.date(month_start.year, month_start.month + 1, 10)


# ---------------------------------------------------------------------------
# Report 1 — Residents who haven't paid their MONTHLY iuran for a given month
# ---------------------------------------------------------------------------

def report_unpaid_monthly(period: str, as_of: datetime.date | None = None) -> list[dict]:
    """
    Returns users who have an active MONTHLY tariff for `period` but no
    matching MONTHLY payment as of `as_of`.

    Each row: { user_id, username, nominal }
    """
    as_of = as_of or _today()
    period_date = _period_to_date(period)

    with connection.cursor() as cur:
        cur.execute("""
            SELECT
                u.id          AS user_id,
                u.username,
                t.nominal
            FROM ql_tariff t
            JOIN auth_user u ON u.id = t.user_id
            WHERE t.kind = 'MONTHLY'
              AND t.start_from <= %s
              AND (t.end_to IS NULL OR t.end_to >= %s)
              AND NOT EXISTS (
                  SELECT 1
                  FROM ql_payment p
                  JOIN ql_paymentbatch pb ON pb.id = p.batch_id
                  WHERE pb.user_id = t.user_id
                    AND p.kind    = 'MONTHLY'
                    AND p.period  = %s
                    AND pb.paid_at::date <= %s
              )
            ORDER BY u.username
        """, [period_date, period_date, period, as_of])
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Report 2 — Residents who haven't paid their GARBAGE iuran for a given month
# ---------------------------------------------------------------------------

def report_unpaid_garbage(period: str, as_of: datetime.date | None = None) -> list[dict]:
    """
    Same logic as report 1 but for GARBAGE tariff / payments.

    Each row: { user_id, username, nominal }
    """
    as_of = as_of or _today()
    period_date = _period_to_date(period)

    with connection.cursor() as cur:
        cur.execute("""
            SELECT
                u.id   AS user_id,
                u.username,
                t.nominal
            FROM ql_tariff t
            JOIN auth_user u ON u.id = t.user_id
            WHERE t.kind = 'GARBAGE'
              AND t.start_from <= %s
              AND (t.end_to IS NULL OR t.end_to >= %s)
              AND NOT EXISTS (
                  SELECT 1
                  FROM ql_payment p
                  JOIN ql_paymentbatch pb ON pb.id = p.batch_id
                  WHERE pb.user_id = t.user_id
                    AND p.kind    = 'GARBAGE'
                    AND p.period  = %s
                    AND pb.paid_at::date <= %s
              )
            ORDER BY u.username
        """, [period_date, period_date, period, as_of])
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Report 3 — Residents who haven't paid dues for earmarked fund X
# ---------------------------------------------------------------------------

def report_unpaid_earmarked(fund_id: int, as_of: datetime.date | None = None) -> list[dict]:
    """
    Compares fund_dues (what each resident owes) against cash_entries(IN)
    for that fund recorded up to `as_of`.

    Only meaningful for funds that have FundDue rows; purely voluntary funds
    will always return an empty list.

    Each row: { user_id, username, expected_amount, paid_amount, shortfall }
    """
    as_of = as_of or _today()

    with connection.cursor() as cur:
        cur.execute("""
            SELECT
                u.id            AS user_id,
                u.username,
                fd.expected_amount,
                COALESCE(paid.total, 0) AS paid_amount,
                fd.expected_amount - COALESCE(paid.total, 0) AS shortfall
            FROM ql_funddue fd
            JOIN auth_user u ON u.id = fd.user_id
            LEFT JOIN (
                SELECT user_id, SUM(amount) AS total
                FROM ql_cashentry
                WHERE fund_id   = %s
                  AND direction = 'IN'
                  AND occurred_at::date <= %s
                GROUP BY user_id
            ) paid ON paid.user_id = fd.user_id
            WHERE fd.fund_id = %s
              AND (fd.expected_amount - COALESCE(paid.total, 0)) > 0
            ORDER BY u.username
        """, [fund_id, as_of, fund_id])
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Report 4 — Security payout owed / paid for month M
# ---------------------------------------------------------------------------

def report_security_payout(period: str, as_of: datetime.date | None = None) -> dict:
    """
    Returns obligation (salary rate for that month), total paid, and balance.

    { period, obligation, paid, balance (positive = still owed) }
    """
    as_of = as_of or _today()
    period_date = _period_to_date(period)

    with connection.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(sr.amount, 0)
            FROM ql_salaryrate sr
            WHERE sr.payee      = 'SECURITY'
              AND sr.start_from <= %s
              AND (sr.end_to IS NULL OR sr.end_to >= %s)
            ORDER BY sr.start_from DESC
            LIMIT 1
        """, [period_date, period_date])
        row = cur.fetchone()
        obligation = Decimal(row[0]) if row else Decimal(0)

        cur.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM ql_payout
            WHERE payee       = 'SECURITY'
              AND period      = %s
              AND payout_date <= %s
        """, [period, as_of])
        paid = Decimal(cur.fetchone()[0])

    return {
        'period':     period,
        'obligation': obligation,
        'paid':       paid,
        'balance':    obligation - paid,
    }


# ---------------------------------------------------------------------------
# Report 5 — Sanitation payout schedule for month M
# Applies the 10/25 timing rule in Python; returns one row per payout date.
# ---------------------------------------------------------------------------

def report_sanitation_payout(period: str, as_of: datetime.date | None = None) -> list[dict]:
    """
    For each garbage payment with period = M paid on or before `as_of`,
    computes the scheduled payout date using the timing rule, then joins
    against actual payouts recorded.

    Each row: { payout_date, expected_amount, actual_paid, balance }
    """
    as_of = as_of or _today()

    # Fetch all garbage payments for this period
    payments = (
        Payment.objects
        .filter(kind=Payment.Kind.GARBAGE, period=period, batch__paid_at__date__lte=as_of)
        .select_related('batch')
        .values('nominal', 'batch__paid_at')
    )

    # Group by computed payout date
    schedule: dict[datetime.date, Decimal] = {}
    for p in payments:
        pd = _garbage_payout_date(period, p['batch__paid_at'])
        if pd <= as_of:
            schedule[pd] = schedule.get(pd, Decimal(0)) + p['nominal']

    if not schedule:
        return []

    # Fetch actual payouts for this period
    actual = {
        row['payout_date']: row['total']
        for row in Payout.objects
            .filter(payee=Payout.Payee.SANITATION, period=period, payout_date__lte=as_of)
            .values('payout_date')
            .annotate(total=Sum('amount'))
    }

    return [
        {
            'payout_date':     pd,
            'expected_amount': expected,
            'actual_paid':     actual.get(pd, Decimal(0)),
            'balance':         expected - actual.get(pd, Decimal(0)),
        }
        for pd, expected in sorted(schedule.items())
    ]


# ---------------------------------------------------------------------------
# Report 6 — Security debt outstanding as of date D
# ---------------------------------------------------------------------------

def report_security_debt(as_of: datetime.date | None = None) -> dict:
    """
    Derived: Σ obligations(all months up to as_of) − Σ payouts(SECURITY, payout_date <= as_of)

    Returns:
        { total_obligation, total_paid, debt (positive = RT owes the guard) }
    """
    as_of = as_of or _today()

    with connection.cursor() as cur:
        # Sum obligation month-by-month from the first salary rate through as_of
        cur.execute("""
            WITH months AS (
                SELECT to_char(
                    generate_series(
                        DATE_TRUNC('month', (SELECT MIN(start_from) FROM ql_salaryrate WHERE payee = 'SECURITY')),
                        DATE_TRUNC('month', %s::date),
                        '1 month'
                    ),
                    'YYYY-MM'
                ) AS m
            ),
            obligations AS (
                SELECT
                    months.m,
                    (
                        SELECT sr.amount
                        FROM ql_salaryrate sr
                        WHERE sr.payee = 'SECURITY'
                          AND sr.start_from <= (months.m || '-01')::date
                          AND (sr.end_to IS NULL OR sr.end_to >= (months.m || '-01')::date)
                        ORDER BY sr.start_from DESC
                        LIMIT 1
                    ) AS obligation
                FROM months
            )
            SELECT COALESCE(SUM(obligation), 0) FROM obligations
        """, [as_of])
        total_obligation = Decimal(cur.fetchone()[0])

        cur.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM ql_payout
            WHERE payee       = 'SECURITY'
              AND payout_date <= %s
        """, [as_of])
        total_paid = Decimal(cur.fetchone()[0])

    return {
        'as_of':            as_of,
        'total_obligation': total_obligation,
        'total_paid':       total_paid,
        'debt':             total_obligation - total_paid,
    }


# ---------------------------------------------------------------------------
# Report 7 — Balance per fund as of date D
# ---------------------------------------------------------------------------

def report_fund_balances(as_of: datetime.date | None = None) -> list[dict]:
    """
    Computes balance for every fund using the formulas:

    GENERAL   = Σ MONTHLY payments + Σ cash_entries(GENERAL, IN)
              − Σ payouts(SECURITY)  − Σ cash_entries(GENERAL, OUT)
    GARBAGE   = Σ GARBAGE payments  − Σ payouts(SANITATION)
    EARMARKED = Σ cash_entries(X, IN) − Σ cash_entries(X, OUT)

    Each row: { fund_id, name, kind, balance }
    """
    as_of = as_of or _today()

    with connection.cursor() as cur:
        cur.execute("""
            WITH
            -- MONTHLY payments → General fund
            monthly_in AS (
                SELECT COALESCE(SUM(p.nominal), 0) AS total
                FROM ql_payment p
                JOIN ql_paymentbatch pb ON pb.id = p.batch_id
                WHERE p.kind = 'MONTHLY'
                  AND pb.paid_at::date <= %s
            ),
            -- GARBAGE payments → Garbage fund
            garbage_in AS (
                SELECT COALESCE(SUM(p.nominal), 0) AS total
                FROM ql_payment p
                JOIN ql_paymentbatch pb ON pb.id = p.batch_id
                WHERE p.kind = 'GARBAGE'
                  AND pb.paid_at::date <= %s
            ),
            -- Security payouts (reduce General)
            security_out AS (
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM ql_payout
                WHERE payee = 'SECURITY'
                  AND payout_date <= %s
            ),
            -- Sanitation payouts (reduce Garbage)
            sanitation_out AS (
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM ql_payout
                WHERE payee = 'SANITATION'
                  AND payout_date <= %s
            ),
            -- Cash entry totals per fund/direction
            cash AS (
                SELECT
                    fund_id,
                    direction,
                    COALESCE(SUM(amount), 0) AS total
                FROM ql_cashentry
                WHERE occurred_at::date <= %s
                GROUP BY fund_id, direction
            )
            SELECT
                f.id,
                f.name,
                f.kind,
                CASE f.kind
                    WHEN 'GENERAL' THEN
                        (SELECT total FROM monthly_in)
                        + COALESCE((SELECT total FROM cash WHERE fund_id = f.id AND direction = 'IN'), 0)
                        - (SELECT total FROM security_out)
                        - COALESCE((SELECT total FROM cash WHERE fund_id = f.id AND direction = 'OUT'), 0)
                    WHEN 'GARBAGE' THEN
                        (SELECT total FROM garbage_in)
                        - (SELECT total FROM sanitation_out)
                    ELSE
                        COALESCE((SELECT total FROM cash WHERE fund_id = f.id AND direction = 'IN'), 0)
                        - COALESCE((SELECT total FROM cash WHERE fund_id = f.id AND direction = 'OUT'), 0)
                END AS balance
            FROM ql_fund f
            ORDER BY f.kind, f.name
        """, [as_of, as_of, as_of, as_of, as_of])
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
