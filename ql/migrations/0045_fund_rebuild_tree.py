from django.db import migrations


def rebuild_fund_tree(apps, schema_editor):
    # django-mptt's rebuild() relies on manager/tree-metadata that historical
    # models from apps.get_model() don't carry, so import the real model.
    from ql.models import Fund
    Fund.objects.rebuild()


class Migration(migrations.Migration):

    dependencies = [
        ('ql', '0044_fund_nested_set'),
    ]

    operations = [
        migrations.RunPython(rebuild_fund_tree, migrations.RunPython.noop),
    ]
