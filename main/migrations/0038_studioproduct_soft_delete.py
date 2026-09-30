# Generated for ZAD Studio soft-delete audit trail.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0037_studio_team_portal"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="studioproduct",
            name="status",
            field=models.CharField(
                choices=[
                    ("AVAILABLE", "موجود"),
                    ("SOLD", "فروخته شده"),
                    ("WITHDRAWN", "کشیده شده"),
                    ("CANCELLED", "لغو شده"),
                    ("DELETED", "حذف مدیریتی"),
                ],
                db_index=True,
                default="AVAILABLE",
                max_length=12,
                verbose_name="وضعیت",
            ),
        ),
        migrations.AddField(
            model_name="studioproduct",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="زمان حذف مدیریتی"),
        ),
        migrations.AddField(
            model_name="studioproduct",
            name="deleted_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="studio_deleted_entries", to=settings.AUTH_USER_MODEL,
                verbose_name="حذف‌شده توسط",
            ),
        ),
        migrations.AddField(
            model_name="studioproduct",
            name="deletion_reason",
            field=models.TextField(blank=True, verbose_name="علت حذف مدیریتی"),
        ),
    ]
