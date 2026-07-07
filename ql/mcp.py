from mcp_server import ModelQueryToolset

from .models import (
    Fund, SalaryRate, Setting, Tariff,
    PaymentBatch, Payment, Payout, CashEntry, FundDue,
)


class FundToolset(ModelQueryToolset):
    model = Fund
    extra_instructions = (
        "Fund is a money pool. kind is one of GENERAL (main kas RT), "
        "GARBAGE (pass-through for garbage fees), or EARMARKED (voluntary / special purpose). "
        "Only one GENERAL and one GARBAGE fund may exist at a time. "
        "Use status=OPEN to filter active funds."
    )


class SalaryRateToolset(ModelQueryToolset):
    model = SalaryRate
    extra_instructions = (
        "Append-only effective-dated salary table for security guards. "
        "The currently active rate has end_to=null. "
        "Do NOT mutate existing rows; close the current row then insert a new one."
    )


class SettingToolset(ModelQueryToolset):
    model = Setting
    extra_instructions = (
        "Runtime-configurable key/value constants. "
        "Known keys: security_day (day-of-month security is paid), "
        "garbage_days (comma-separated days garbage fee is collected)."
    )


class TariffToolset(ModelQueryToolset):
    model = Tariff
    extra_instructions = (
        "Agreed monthly payment amount per resident per kind (MONTHLY or GARBAGE). "
        "Append-only; the active tariff for a resident has end_to=null. "
        "nominal is the historical agreed amount — never back-calculate from current tariffs."
    )


class PaymentBatchToolset(ModelQueryToolset):
    model = PaymentBatch
    extra_instructions = (
        "One collection event (resident visit). "
        "A batch groups one or more Payment rows, e.g. a resident paying 3 months of garbage at once. "
        "paid_at is the actual payment datetime."
    )


class PaymentToolset(ModelQueryToolset):
    model = Payment
    extra_instructions = (
        "One period's money within a PaymentBatch. Append-only. "
        "nominal can be negative for a reversal row. "
        "period is YYYY-MM. kind MONTHLY maps to the General fund; GARBAGE maps to the Garbage fund. "
        "nominal is a frozen historical fact; never derive it from current tariffs."
    )


class PayoutToolset(ModelQueryToolset):
    model = Payout
    extra_instructions = (
        "Money paid out to a SECURITY guard or SANITATION worker. "
        "period is YYYY-MM indicating which month the payout covers."
    )


class CashEntryToolset(ModelQueryToolset):
    model = CashEntry
    extra_instructions = (
        "General ledger rows tied to a specific Fund. "
        "direction IN = income (user is the contributor, required). "
        "direction OUT = expense (user is the responsible person, optional). "
        "creator is whoever recorded the entry and may differ from user."
    )


class FundDueToolset(ModelQueryToolset):
    model = FundDue
    extra_instructions = (
        "Expected contribution per resident per earmarked Fund. "
        "Used as the denominator when calculating unpaid balances. "
        "A fund with no FundDue rows has no concept of 'unpaid'."
    )
