from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0010_workshop_page_content_sections"),
    ]

    operations = [
        migrations.CreateModel(
            name="PageContentBlock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخرین ویرایش")),
                ("page", models.CharField(choices=[("home", "خانه"), ("flowers", "گل‌ها"), ("bakery", "بیکری"), ("gifts", "هدایا"), ("occasions", "مناسبت‌ها"), ("workshops", "ورکشاپ‌ها"), ("about", "درباره زاد"), ("contact", "تماس با ما"), ("faq", "سوالات پرتکرار"), ("blog", "بلاگ"), ("mashhad", "صفحات مشهد"), ("product", "صفحه محصول"), ("subcategory", "صفحه زیردسته"), ("occasion-detail", "جزئیات مناسبت"), ("event-detail", "جزئیات ورکشاپ"), ("blog-detail", "جزئیات بلاگ")], db_index=True, max_length=40, verbose_name="صفحه")),
                ("section_key", models.SlugField(help_text="یک کلید انگلیسی پایدار؛ مثل intro، story، cta یا empty.", max_length=80, verbose_name="کلید بخش")),
                ("kicker", models.CharField(blank=True, max_length=140, verbose_name="عنوان کوتاه")),
                ("title", models.CharField(blank=True, max_length=240, verbose_name="عنوان")),
                ("body", models.TextField(blank=True, verbose_name="متن")),
                ("cta_text", models.CharField(blank=True, max_length=100, verbose_name="متن دکمه")),
                ("cta_url", models.CharField(blank=True, help_text="مسیر داخلی مثل /contact/#lead-form یا آدرس کامل https://...", max_length=300, verbose_name="لینک دکمه")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="فعال باشد؟")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="ترتیب نمایش")),
            ],
            options={
                "verbose_name": "متن قابل ویرایش صفحه",
                "verbose_name_plural": "متن‌های قابل ویرایش صفحات",
                "ordering": ["page", "sort_order", "section_key"],
                "indexes": [models.Index(fields=["page", "is_active", "sort_order"], name="page_content_lookup_idx")],
                "constraints": [models.UniqueConstraint(fields=("page", "section_key"), name="uniq_page_content_block")],
            },
        ),
    ]
