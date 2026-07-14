from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ql', '0036_add_all_transaction_proxy'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='highlight',
            field=models.CharField(
                blank=True,
                choices=[('', 'None'), ('warning', 'Warning'), ('danger', 'Danger')],
                default='',
                max_length=10,
            ),
        ),
    ]
