import django.utils.timezone
from django.db import migrations, models


_ADD = django.utils.timezone.now
_PRESERVE = False  # drop default after migration


class Migration(migrations.Migration):

    dependencies = [
        ('ql', '0004_add_payment_batch_created_at'),
    ]

    operations = [
        # ---- models that need BOTH fields ----
        *[
            op
            for table, model in [
                ('cash_entries',   'cashentry'),
                ('fund_dues',      'funddue'),
                ('payments',       'payment'),
                ('payouts',        'payout'),
                ('salary_rates',   'salaryrate'),
                ('settings',       'setting'),
                ('tariffs',        'tariff'),
                ('user_properties','userproperty'),
            ]
            for op in [
                migrations.AddField(
                    model_name=model,
                    name='created_at',
                    field=models.DateTimeField(auto_now_add=True, default=_ADD),
                    preserve_default=_PRESERVE,
                ),
                migrations.AddField(
                    model_name=model,
                    name='updated_at',
                    field=models.DateTimeField(auto_now=True),
                ),
            ]
        ],

        # ---- Fund: already has created_at, only needs updated_at ----
        migrations.AddField(
            model_name='fund',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),

        # ---- PaymentBatch: already has created_at (migration 0004), only needs updated_at ----
        migrations.AddField(
            model_name='paymentbatch',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
