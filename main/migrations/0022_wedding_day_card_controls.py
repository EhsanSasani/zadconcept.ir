from django.db import migrations, models

import main.models


class Migration(migrations.Migration):
    dependencies = [("main", "0021_restore_wedding_proposal_separator")]

    operations = [
        migrations.AddField(
            model_name="weddingpagecontent",
            name="bridal_bouquet_card_image",
            field=models.ImageField(
                blank=True,
                help_text="اختیاری؛ اگر خالی باشد تصویر محصول یا تصویر پیش‌فرض نمایش داده می‌شود.",
                null=True,
                upload_to=main.models.wedding_bridal_bouquet_card_upload_to,
                verbose_name="تصویر کارت دسته‌گل عروس",
            ),
        ),
        migrations.AddField(
            model_name="weddingpagecontent",
            name="bridal_bouquet_card_kicker",
            field=models.CharField(
                blank=True,
                default="BRIDAL BOUQUETS",
                help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
                max_length=100,
                verbose_name="عنوان انگلیسی کارت دسته‌گل عروس",
            ),
        ),
        migrations.AddField(
            model_name="weddingpagecontent",
            name="bridal_bouquet_card_text",
            field=models.TextField(
                blank=True,
                default="طراحی دسته‌گل عروس متناسب با استایل، فصل و پالت رنگ روز عروسی.",
                help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
                verbose_name="توضیح کارت دسته‌گل عروس",
            ),
        ),
        migrations.AddField(
            model_name="weddingpagecontent",
            name="bridal_bouquet_card_title",
            field=models.CharField(
                blank=True,
                default="دسته‌گل عروس",
                help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
                max_length=180,
                verbose_name="عنوان فارسی کارت دسته‌گل عروس",
            ),
        ),
        migrations.AddField(
            model_name="weddingpagecontent",
            name="wedding_car_card_image",
            field=models.ImageField(
                blank=True,
                help_text="اختیاری؛ اگر خالی باشد تصویر محصول یا تصویر پیش‌فرض نمایش داده می‌شود.",
                null=True,
                upload_to=main.models.wedding_car_card_upload_to,
                verbose_name="تصویر کارت ماشین عروس",
            ),
        ),
        migrations.AddField(
            model_name="weddingpagecontent",
            name="wedding_car_card_kicker",
            field=models.CharField(
                blank=True,
                default="WEDDING CARS",
                help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
                max_length=100,
                verbose_name="عنوان انگلیسی کارت ماشین عروس",
            ),
        ),
        migrations.AddField(
            model_name="weddingpagecontent",
            name="wedding_car_card_text",
            field=models.TextField(
                blank=True,
                default="گل‌آرایی اختصاصی خودرو با توجه به مدل ماشین، فصل و سبک مراسم.",
                help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
                verbose_name="توضیح کارت ماشین عروس",
            ),
        ),
        migrations.AddField(
            model_name="weddingpagecontent",
            name="wedding_car_card_title",
            field=models.CharField(
                blank=True,
                default="ماشین عروس",
                help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
                max_length=180,
                verbose_name="عنوان فارسی کارت ماشین عروس",
            ),
        ),
    ]
