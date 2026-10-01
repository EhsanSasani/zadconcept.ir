from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0038_studioproduct_soft_delete"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudioAdminNotification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")),
                (
                    "event",
                    models.CharField(
                        choices=[
                            ("CREATED", "ثبت محصول"),
                            ("PRICE", "تغییر قیمت"),
                            ("STATUS", "تغییر وضعیت"),
                            ("DELETED", "حذف مدیریتی"),
                        ],
                        max_length=12,
                    ),
                ),
                ("chat_id", models.BigIntegerField()),
                ("caption", models.CharField(max_length=1024)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "در صف"),
                            ("SENDING", "در حال ارسال"),
                            ("RETRY", "تلاش مجدد"),
                            ("SENT", "ارسال شد"),
                            ("UNCERTAIN", "نیازمند بررسی"),
                            ("FAILED", "ناموفق"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=12,
                    ),
                ),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("lock_token", models.UUIDField(blank=True, editable=False, null=True)),
                ("telegram_message_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=64)),
                (
                    "record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="admin_notifications",
                        to="main.studioproduct",
                    ),
                ),
            ],
            options={
                "verbose_name": "اعلان خصوصی استودیو",
                "verbose_name_plural": "اعلان‌های خصوصی استودیو",
                "ordering": ["next_attempt_at", "pk"],
                "indexes": [
                    models.Index(fields=["status", "next_attempt_at"], name="studio_admin_notify_due"),
                    models.Index(fields=["record", "created_at"], name="studio_admin_notify_record"),
                ],
            },
        ),
    ]
