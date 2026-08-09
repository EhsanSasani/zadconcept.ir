from django.db import migrations, models

import main.models


COLLECTION_DEFAULTS = {
    "proposal-bouquets": {
        "hero_kicker": "PROPOSAL BOUQUETS",
        "hero_title": "دسته‌گل خواستگاری و بله‌برون",
        "hero_text": "دسته‌گل‌هایی هماهنگ با فضای خواستگاری و بله‌برون؛ با امکان هماهنگی رنگ، فرم و بودجه.",
        "hero_alt_text": "دسته‌گل خواستگاری و بله‌برون زاد",
    },
    "proposal-sweets": {
        "hero_kicker": "PROPOSAL SWEETS",
        "hero_title": "شیرینی خواستگاری و بله‌برون",
        "hero_text": "شیرینی‌های منتخب برای پذیرایی و هدیه، با امکان هماهنگی تعداد و چیدمان.",
        "hero_alt_text": "شیرینی خواستگاری و بله‌برون زاد",
    },
    "bridal-bouquets": {
        "hero_kicker": "BRIDAL BOUQUETS",
        "hero_title": "دسته‌گل عروس",
        "hero_text": "طراحی دسته‌گل عروس متناسب با استایل، فصل و پالت رنگ روز عروسی.",
        "hero_alt_text": "دسته‌گل عروس زاد",
    },
    "wedding-cars": {
        "hero_kicker": "WEDDING CARS",
        "hero_title": "ماشین عروس",
        "hero_text": "گل‌آرایی اختصاصی خودرو با توجه به مدل ماشین، فصل و سبک مراسم.",
        "hero_alt_text": "گل‌آرایی ماشین عروس زاد",
    },
}


def seed_collection_content(apps, schema_editor):
    WeddingCollectionContent = apps.get_model("main", "WeddingCollectionContent")
    for collection_key, defaults in COLLECTION_DEFAULTS.items():
        WeddingCollectionContent.objects.update_or_create(
            collection_key=collection_key,
            defaults=defaults,
        )


def remove_seeded_collection_content(apps, schema_editor):
    WeddingCollectionContent = apps.get_model("main", "WeddingCollectionContent")
    WeddingCollectionContent.objects.filter(
        collection_key__in=COLLECTION_DEFAULTS.keys()
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("main", "0022_wedding_day_card_controls")]

    operations = [
        migrations.CreateModel(
            name="WeddingCollectionContent",
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
                    "collection_key",
                    models.CharField(
                        choices=[
                            ("proposal-bouquets", "دسته‌گل خواستگاری و بله‌برون"),
                            ("proposal-sweets", "شیرینی خواستگاری و بله‌برون"),
                            ("bridal-bouquets", "دسته‌گل عروس"),
                            ("wedding-cars", "ماشین عروس"),
                        ],
                        max_length=40,
                        unique=True,
                        verbose_name="صفحه مجموعه",
                    ),
                ),
                (
                    "hero_image",
                    models.ImageField(
                        blank=True,
                        help_text="اختیاری؛ اگر خالی باشد تصویر اولین محصول یا تصویر پیش‌فرض استفاده می‌شود.",
                        null=True,
                        upload_to=main.models.wedding_collection_hero_upload_to,
                        verbose_name="تصویر Hero دسکتاپ",
                    ),
                ),
                (
                    "hero_mobile_image",
                    models.ImageField(
                        blank=True,
                        help_text="اختیاری؛ اگر خالی باشد تصویر دسکتاپ استفاده می‌شود.",
                        null=True,
                        upload_to=main.models.wedding_collection_hero_mobile_upload_to,
                        verbose_name="تصویر Hero موبایل",
                    ),
                ),
                (
                    "hero_kicker",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="اختیاری است؛ برای Hero بدون متن خالی بگذارید.",
                        max_length=100,
                        verbose_name="عنوان انگلیسی Hero",
                    ),
                ),
                (
                    "hero_title",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="اختیاری است؛ برای Hero فقط‌تصویر خالی بگذارید.",
                        max_length=220,
                        verbose_name="عنوان فارسی Hero",
                    ),
                ),
                (
                    "hero_text",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="اختیاری است؛ بهتر است کوتاه و حداکثر دو خط باشد.",
                        verbose_name="توضیح Hero",
                    ),
                ),
                (
                    "hero_alt_text",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="اختیاری؛ برای دسترس‌پذیری و سئو تصویر.",
                        max_length=180,
                        verbose_name="متن جایگزین تصویر Hero",
                    ),
                ),
                (
                    "seo_title",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=180,
                        verbose_name="SEO Title",
                    ),
                ),
                (
                    "meta_description",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=320,
                        verbose_name="Meta Description",
                    ),
                ),
            ],
            options={
                "verbose_name": "تنظیمات صفحه مجموعه عروسی",
                "verbose_name_plural": "تنظیمات صفحات مجموعه‌های عروسی",
                "ordering": ["collection_key"],
            },
        ),
        migrations.RunPython(
            seed_collection_content,
            remove_seeded_collection_content,
        ),
    ]
