from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0013_zad_v14"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="samedayflower",
            options={
                "ordering": ["sort_order", "-updated_at"],
                "proxy": True,
                "verbose_name": "گل ارسال روز",
                "verbose_name_plural": "مدیریت ارسال روز",
            },
        ),
    ]
