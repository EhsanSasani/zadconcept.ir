from django.db import migrations, models
import django.db.models.deletion
import main.models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0025_same_day_catalog_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="workshop_type",
            field=models.CharField(
                choices=[
                    ("educational", "آموزشی"),
                    ("experience", "تجربه‌محور"),
                    ("gathering", "دورهمی"),
                ],
                db_index=True,
                default="experience",
                max_length=20,
                verbose_name="نوع ورکشاپ",
            ),
        ),
        migrations.CreateModel(
            name="WorkshopGalleryImage",
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
                    "image",
                    models.ImageField(
                        upload_to=main.models.workshop_gallery_upload_to,
                        verbose_name="تصویر",
                    ),
                ),
                (
                    "alt_text",
                    models.CharField(
                        blank=True,
                        max_length=180,
                        verbose_name="متن جایگزین",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="ترتیب نمایش",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        verbose_name="فعال باشد؟",
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gallery_images",
                        to="main.event",
                        verbose_name="ورکشاپ",
                    ),
                ),
            ],
            options={
                "verbose_name": "تصویر گالری ورکشاپ",
                "verbose_name_plural": "گالری ورکشاپ‌ها",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="workshopgalleryimage",
            index=models.Index(
                fields=["is_active", "sort_order"],
                name="workshop_gallery_active_idx",
            ),
        ),
    ]
