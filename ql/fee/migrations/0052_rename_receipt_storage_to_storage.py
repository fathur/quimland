from django.db import migrations


class Migration(migrations.Migration):
    """Hand-written: makemigrations would offer a RemoveField+AddField pair
    for a --no-input run instead of detecting the rename, which would reset
    every row back to the field's 'local' default and lose which ones are
    actually on R2. RenameField preserves the column's existing values."""

    dependencies = [
        ('fee', '0051_asset_receipt_storage_duenoteproof_receipt_storage_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='receipt',
            old_name='receipt_storage',
            new_name='storage',
        ),
        migrations.RenameField(
            model_name='asset',
            old_name='receipt_storage',
            new_name='storage',
        ),
        migrations.RenameField(
            model_name='duenoteproof',
            old_name='receipt_storage',
            new_name='storage',
        ),
    ]
