from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0009_workshoppagecontent_alter_tag_is_occasion"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshoppagecontent",
            name="types_kicker",
            field=models.CharField(blank=True, default="", max_length=120, verbose_name="عنوان کوتاه انواع ورکشاپ"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="types_title",
            field=models.CharField(blank=True, default="", max_length=220, verbose_name="عنوان انواع ورکشاپ"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="public_title",
            field=models.CharField(blank=True, default="", max_length=160, verbose_name="عنوان ورکشاپ عمومی"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="public_text",
            field=models.TextField(blank=True, default="", verbose_name="متن ورکشاپ عمومی"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="private_title",
            field=models.CharField(blank=True, default="", max_length=160, verbose_name="عنوان ورکشاپ خصوصی"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="private_text",
            field=models.TextField(blank=True, default="", verbose_name="متن ورکشاپ خصوصی"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="corporate_title",
            field=models.CharField(blank=True, default="", max_length=160, verbose_name="عنوان ورکشاپ سازمانی"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="corporate_text",
            field=models.TextField(blank=True, default="", verbose_name="متن ورکشاپ سازمانی"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="upcoming_kicker",
            field=models.CharField(blank=True, default="", max_length=120, verbose_name="عنوان کوتاه برنامه‌های آینده"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="upcoming_title",
            field=models.CharField(blank=True, default="", max_length=220, verbose_name="عنوان برنامه‌های آینده"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="upcoming_empty_title",
            field=models.CharField(blank=True, default="", max_length=220, verbose_name="عنوان حالت بدون برنامه"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="workshoppagecontent",
            name="upcoming_empty_text",
            field=models.TextField(blank=True, default="", verbose_name="متن حالت بدون برنامه"),
            preserve_default=False,
        ),
    ]
