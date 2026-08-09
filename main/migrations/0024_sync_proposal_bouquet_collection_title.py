from django.db import migrations


OLD_TITLE = "دسته‌گل خواستگاری و بله‌برون"
CURRENT_TITLE = "گل‌های خواستگاری و بله‌برون"


def use_current_title(apps, schema_editor):
    WeddingCollectionContent = apps.get_model("main", "WeddingCollectionContent")
    WeddingCollectionContent.objects.filter(
        collection_key="proposal-bouquets",
        hero_title=OLD_TITLE,
    ).update(hero_title=CURRENT_TITLE)


def restore_seed_title(apps, schema_editor):
    WeddingCollectionContent = apps.get_model("main", "WeddingCollectionContent")
    WeddingCollectionContent.objects.filter(
        collection_key="proposal-bouquets",
        hero_title=CURRENT_TITLE,
    ).update(hero_title=OLD_TITLE)


class Migration(migrations.Migration):
    dependencies = [("main", "0023_wedding_collection_content")]

    operations = [
        migrations.RunPython(use_current_title, restore_seed_title),
    ]
