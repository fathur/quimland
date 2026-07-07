from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ql', '0012_paymentbatch_nominal'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentbatch',
            name='receipt_storage',
            field=models.CharField(
                choices=[('local', 'Local'), ('r2', 'Cloudflare R2')],
                default='local',
                editable=False,
                help_text='Backend that holds the receipt file.',
                max_length=10,
            ),
        ),
    ]
