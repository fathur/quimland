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
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker (Redis) |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Celery result backend (Redis) |

## Celery

Background tasks live in each app's `tasks.py` (e.g. `ql/tasks.py`), wired up via
`config/celery.py`. Needs a Redis instance reachable at `CELERY_BROKER_URL`.

```bash
# Worker (run alongside `manage.py runserver`)
poetry run celery -A config worker -l info

# Beat — needed for scheduled tasks (e.g. the daily resident access sync)
poetry run celery -A config beat -l info

# Quick sanity check from a Django shell
poetry run python manage.py shell
from ql.tasks import debug_task
debug_task.delay()
```

### Scheduled tasks

The schedule is stored in the database via `django-celery-beat`, not just in
code — manage it from **/admin/ → Periodic Tasks** (crontab/interval editing,
enable/disable, "run now" via a clocked task), no redeploy needed. The
`CELERY_BEAT_SCHEDULE` dict in `config/settings.py` is only a one-time seed:
on first `celery beat` run it's copied into the DB if not already there, then
ignored — from then on the DB (i.e. the admin) is the source of truth.

| Task | Default schedule | Purpose |
|---|---|---|
| `ql.tasks.access_control.sync_resident_admin_access` | daily, 01:00 | Grants admin (`is_staff`) login to residents with no outstanding ROUTINE dues, revokes it from those who owe. Superusers are never touched; `is_active` is never touched. |

### Production (systemd)

Run the worker and beat as long-lived services instead of `poetry run ...` in
a terminal. Point systemd straight at the Poetry virtualenv's `celery`
binary — don't invoke `poetry run` from the unit, it adds a needless resolve
step on every start.

```bash
# One-time: keep the venv inside the project so its path is stable
# (otherwise Poetry hides it under ~/.cache/pypoetry/virtualenvs/<hash>/).
cd /opt/quimland                      # wherever you deployed the repo
poetry config virtualenvs.in-project true
poetry install                        # recreates the venv at ./.venv
```

Create a dedicated, unprivileged user to run the services (adjust paths/user
to match your deploy):

```bash
sudo useradd --system --home /opt/quimland --shell /usr/sbin/nologin quimland
sudo chown -R quimland:quimland /opt/quimland
```

`/etc/systemd/system/quimland-celery.service` — the worker:

```ini
[Unit]
Description=Quimland Celery worker
After=network.target redis-server.service postgresql.service

[Service]
Type=simple
User=quimland
Group=quimland
WorkingDirectory=/opt/quimland
EnvironmentFile=/opt/quimland/.env
ExecStart=/opt/quimland/.venv/bin/celery -A config worker -l info
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/quimland-celerybeat.service` — the scheduler (needs the
same `django-celery-beat` DB tables migrated first, see above):

```ini
[Unit]
Description=Quimland Celery beat
After=network.target redis-server.service postgresql.service

[Service]
Type=simple
User=quimland
Group=quimland
WorkingDirectory=/opt/quimland
EnvironmentFile=/opt/quimland/.env
ExecStart=/opt/quimland/.venv/bin/celery -A config beat -l info
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`EnvironmentFile=` is there so `DB_*`/`CELERY_BROKER_URL`/etc. are set before
Django's settings module (and its own `load_dotenv(BASE_DIR / '.env')`) even
runs — belt-and-suspenders with the `.env` file already living in
`WorkingDirectory`; keep both pointed at the same file or drop one.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now quimland-celery quimland-celerybeat

# Status / logs
sudo systemctl status quimland-celery quimland-celerybeat
journalctl -u quimland-celery -f
journalctl -u quimland-celerybeat -f

# After deploying new code
sudo systemctl restart quimland-celery quimland-celerybeat
```

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
Implemented in `ql/services/queries.py :: _garbage_payout_date()`.

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

## Reports (in `ql/services/queries.py`)

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

from ql.services.queries import *
import datetime

report_unpaid_monthly('2026-05')
report_sanitation_payout('2026-06')
report_security_debt(datetime.date(2026, 6, 26))
report_fund_balances()
```
