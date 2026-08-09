from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0019_wedding_proposal_card_images")]

    operations = [
        migrations.AlterField(
            model_name="weddingpagecontent",
            name="proposal_title",
            field=models.CharField(
                blank=True,
                default="",
                help_text="اختیاری است؛ اگر خالی باشد عنوان فارسی این بخش نمایش داده نمی‌شود.",
                max_length=220,
                verbose_name="عنوان بخش خواستگاری و بله‌برون",
            ),
        ),
        migrations.AlterField(
            model_name="weddingpagecontent",
            name="proposal_text",
            field=models.TextField(
                blank=True,
                default="",
                help_text="اختیاری است؛ می‌توانید برای طراحی مینیمال این فیلد را خالی بگذارید.",
                verbose_name="توضیح بخش خواستگاری و بله‌برون",
            ),
        ),
    ]
