from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0033_telegram_group_products")]
    operations = [
        migrations.AddField(
            model_name="telegramsamedaypost", name="deleted_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name="telegramsamedaypost", name="product",
            field=models.OneToOneField(
                to="main.product", null=True, blank=True,
                on_delete=models.SET_NULL, related_name="telegram_same_day_post",
            ),
        ),
    ]
