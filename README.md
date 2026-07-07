# Quimland — RT Finance System

## Stack
- **Django 6** · **PostgreSQL** · Poetry

## First-time setup

```bash
# 1. Install dependencies
poetry install

# 2. Copy and fill in DB credentials
cp .env.example .env        # edit DB_NAME, DB_USER, DB_PASSWORD, DB_HOST

# 3. Run migrations
poetry run python manage.py migrate

# 4. Seed demo data (demonstrates late + advance garbage payment cases)
poetry run python manage.py seed_finance

# 5. (Optional) Create a superuser for the admin
poetry run python manage.py createsuperuser
```

## Environment variables

| Variable      | Default      | Description                              |
|---------------|--------------|------------------------------------------|
| `DB_NAME`     | `quimland`   | Postgres database name                   |
| `DB_USER`     | `postgres`   | Postgres user                            |
| `DB_PASSWORD` | *(empty)*    | Postgres password                        |
| `DB_HOST`     | `localhost`  | Postgres host                            |
| `DB_PORT`     | `5432`       | Postgres port                            |
| `SECRET_KEY`  | insecure dev | Django secret key — **change for prod**  |
| `DEBUG`       | `True`       | Set to `False` in production             |

To use SQLite for quick local testing (no Postgres needed):
```bash
DB_ENGINE=django.db.backends.sqlite3 poetry run python manage.py migrate
```

## Re-seeding

```bash
poetry run python manage.py seed_finance --reset
```

## Key design decisions

### Two time dimensions on every payment
`period` (YYYY-MM) = the month being paid for.  
`paid_at` = when the money was physically received.  
Never collapse these — they are what make late/advance queries trivial.

### Sanitation timing rule
For a GARBAGE payment with period M received at P:
```
eligible    = max(P.date, day-10 of month M)
payout_date = next of [10, 25] that is >= eligible
```
Implemented in `ql/queries.py :: _garbage_payout_date()`.

### Append-only tables
`payments` and `tariffs` are **never** UPDATE-d or DELETE-d.  
Corrections are reversal rows (negative nominal). This keeps every past
state reconstructable by filtering `paid_at <= D`.

### Fund separation
`MONTHLY` payments → General fund.  
`GARBAGE` payments → Garbage fund (pure pass-through).  
`EARMARKED` funds use `cash_entries` with an explicit `fund_id`.  
The `fund_dues` table is the denominator for earmarked unpaid reports;
a purely voluntary fund has no `fund_dues` rows and therefore no "unpaid" concept.

## Reports (in `ql/queries.py`)

| # | Function | Returns |
|---|----------|---------|
| 1 | `report_unpaid_monthly(period, as_of)` | Users with active MONTHLY tariff but no payment |
| 2 | `report_unpaid_garbage(period, as_of)` | Users with active GARBAGE tariff but no payment |
| 3 | `report_unpaid_earmarked(fund_id, as_of)` | Users whose `fund_due` exceeds their `cash_entries` total |
| 4 | `report_security_payout(period, as_of)` | Obligation vs paid for one month |
| 5 | `report_sanitation_payout(period, as_of)` | Scheduled vs actual payout per date for one month |
| 6 | `report_security_debt(as_of)` | Cumulative security guard debt |
| 7 | `report_fund_balances(as_of)` | Balance for every fund |

All `as_of` parameters default to `today` if omitted.

Example usage from a Django shell:
```python
poetry run python manage.py shell

from ql.queries import *
import datetime

report_unpaid_monthly('2026-05')
report_sanitation_payout('2026-06')
report_security_debt(datetime.date(2026, 6, 26))
report_fund_balances()
```
