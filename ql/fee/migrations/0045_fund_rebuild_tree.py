from django.db import migrations


def rebuild_fund_tree(apps, schema_editor):
    # django-mptt's rebuild() relies on manager/tree-metadata that historical
    # models from apps.get_model() don't carry, so import the real model.
    # On a fresh database there is nothing to rebuild — skip, because the real
    # model also selects columns added by later migrations, which don't exist yet.
    if not apps.get_model('fee', 'Fund')._base_manager.exists():
        return
    from ql.fee.models import Fund
    Fund.objects.rebuild()


class Migration(migrations.Migration):

    dependencies = [
        ('fee', '0044_fund_nested_set'),
    ]

    operations = [
        migrations.RunPython(rebuild_fund_tree, migrations.RunPython.noop),
    ]
