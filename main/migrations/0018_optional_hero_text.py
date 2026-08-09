from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0017_migrate_wedding_catalog")]

    operations = [
        migrations.AlterField(
            model_name="homeheroslide",
            name="title",
            field=models.CharField(blank=True, help_text="اختیاری است؛ برای اسلاید تصویری بدون متن خالی بگذارید.", max_length=180, verbose_name="عنوان"),
        ),
        migrations.AlterField(
            model_name="sitehero",
            name="title",
            field=models.CharField(blank=True, help_text="اختیاری است؛ برای بنر تصویری بدون متن خالی بگذارید.", max_length=180, verbose_name="عنوان"),
        ),
        migrations.AlterField(
            model_name="weddingpagecontent",
            name="hero_title",
            field=models.CharField(blank=True, default="", help_text="اختیاری است؛ برای بنر تصویری بدون متن خالی بگذارید.", max_length=220, verbose_name="عنوان Hero"),
        ),
        migrations.AlterField(
            model_name="weddingpagecontent",
            name="hero_text",
            field=models.TextField(blank=True, default="", help_text="اختیاری است؛ برای بنر تصویری بدون متن خالی بگذارید.", verbose_name="متن Hero"),
        ),
    ]
