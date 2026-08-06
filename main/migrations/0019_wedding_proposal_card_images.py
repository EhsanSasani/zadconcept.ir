from django.db import migrations, models
import main.models


class Migration(migrations.Migration):
    dependencies = [("main", "0018_optional_hero_text")]

    operations = [
        migrations.AddField(
            model_name="weddingpagecontent",
            name="proposal_bouquet_card_image",
            field=models.ImageField(
                blank=True,
                help_text="اختیاری؛ اگر خالی باشد تصویر محصول یا تصویر پیش‌فرض نمایش داده می‌شود.",
                null=True,
                upload_to=main.models.wedding_proposal_bouquet_card_upload_to,
                verbose_name="تصویر کارت دسته‌گل خواستگاری",
            ),
        ),
        migrations.AddField(
            model_name="weddingpagecontent",
            name="proposal_sweets_card_image",
            field=models.ImageField(
                blank=True,
                help_text="اختیاری؛ اگر خالی باشد تصویر محصول یا تصویر پیش‌فرض نمایش داده می‌شود.",
                null=True,
                upload_to=main.models.wedding_proposal_sweets_card_upload_to,
                verbose_name="تصویر کارت شیرینی خواستگاری",
            ),
        ),
    ]
