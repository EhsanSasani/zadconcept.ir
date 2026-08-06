from django.db import migrations, models


DEFAULT_PROPOSAL_TITLE = "خواستگاری و بله‌برون"


def restore_empty_proposal_titles(apps, schema_editor):
    WeddingPageContent = apps.get_model("main", "WeddingPageContent")
    WeddingPageContent.objects.filter(proposal_title="").update(
        proposal_title=DEFAULT_PROPOSAL_TITLE
    )


class Migration(migrations.Migration):
    dependencies = [("main", "0020_optional_wedding_proposal_copy")]

    operations = [
        migrations.RunPython(
            restore_empty_proposal_titles,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="weddingpagecontent",
            name="proposal_title",
            field=models.CharField(
                default=DEFAULT_PROPOSAL_TITLE,
                help_text="عنوان نوار جداکننده بین Hero و دو کارت خواستگاری است.",
                max_length=220,
                verbose_name="عنوان نوار خواستگاری و بله‌برون",
            ),
        ),
        migrations.AlterField(
            model_name="weddingpagecontent",
            name="proposal_text",
            field=models.TextField(
                blank=True,
                default="",
                help_text="اختیاری است و در طراحی فعلی صفحه نمایش داده نمی‌شود.",
                verbose_name="توضیح بخش خواستگاری و بله‌برون",
            ),
        ),
    ]
