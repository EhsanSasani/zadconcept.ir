import django.core.validators
import django.db.models.deletion
import main.models
from django.db import migrations, models
from django.db.models import Q


def _ensure_category(Category, Product, *, name, slug, parent=None, sort_order=0):
    """Create or normalize a category while preserving products on duplicates."""

    candidates = Category.objects.filter(section="flowers")
    by_slug = candidates.filter(slug=slug).first()
    by_name = candidates.filter(name=name).first()

    if by_slug and by_name and by_slug.pk != by_name.pk:
        Product.objects.filter(category_id=by_name.pk).update(category_id=by_slug.pk)
        by_name.name = f"{by_name.name} قدیمی {by_name.pk}"
        by_name.slug = f"{by_name.slug}-legacy-{by_name.pk}"
        by_name.is_active = False
        by_name.save(update_fields=["name", "slug", "is_active", "updated_at"])

    category = by_slug or by_name
    if category is None:
        category = Category(section="flowers")

    category.name = name
    category.slug = slug
    category.parent_id = parent.pk if parent else None
    category.is_active = True
    category.sort_order = sort_order
    category.save()
    return category


def restore_wedding_categories(apps, schema_editor):
    Category = apps.get_model("main", "Category")
    Product = apps.get_model("main", "Product")
    Tag = apps.get_model("main", "Tag")

    wedding = _ensure_category(
        Category,
        Product,
        name="عروسی",
        slug="wedding",
        sort_order=50,
    )
    wedding_car = _ensure_category(
        Category,
        Product,
        name="ماشین عروس",
        slug="wedding-car",
        parent=wedding,
        sort_order=10,
    )
    bridal_bouquet = _ensure_category(
        Category,
        Product,
        name="دسته‌گل عروس",
        slug="bridal-bouquet",
        parent=wedding,
        sort_order=20,
    )

    wedding_tag = Tag.objects.filter(Q(slug="wedding") | Q(name="عروسی")).first()
    wedding_category_ids = list(
        Category.objects.filter(
            section="flowers",
            slug__in=["wedding", "wedding-decoration"],
        ).values_list("pk", flat=True)
    )

    product_ids = set(
        Product.objects.filter(category_id__in=wedding_category_ids).values_list(
            "pk", flat=True
        )
    )
    if wedding_tag:
        product_ids.update(
            wedding_tag.products.filter(category__section="flowers").values_list(
                "pk", flat=True
            )
        )

    persian_car_keywords = ("ماشین", "خودرو", "اتومبیل")
    english_car_tokens = {"car", "vehicle", "auto"}
    for product in Product.objects.filter(pk__in=product_ids).only("pk", "name", "slug"):
        searchable = f"{product.name or ''} {product.slug or ''}".lower()
        english_tokens = set(searchable.replace("-", " ").split())
        is_wedding_car = any(
            word in searchable for word in persian_car_keywords
        ) or bool(english_tokens & english_car_tokens)
        target = wedding_car if is_wedding_car else bridal_bouquet
        Product.objects.filter(pk=product.pk).update(category_id=target.pk)

    if wedding_tag:
        wedding_tag.products.clear()
        wedding_tag.is_occasion = False
        wedding_tag.is_active = False
        wedding_tag.save(update_fields=["is_occasion", "is_active", "updated_at"])

    same_day_by_slug = Tag.objects.filter(slug="same-day").first()
    same_day_by_name = Tag.objects.filter(name="ارسال روز").first()
    if (
        same_day_by_slug
        and same_day_by_name
        and same_day_by_slug.pk != same_day_by_name.pk
    ):
        for product in same_day_by_name.products.all():
            product.tags.add(same_day_by_slug)
        same_day_by_name.name = f"ارسال روز قدیمی {same_day_by_name.pk}"
        same_day_by_name.slug = f"{same_day_by_name.slug}-legacy-{same_day_by_name.pk}"
        same_day_by_name.is_active = False
        same_day_by_name.save()

    same_day = same_day_by_slug or same_day_by_name
    if same_day is None:
        Tag.objects.create(
            name="ارسال روز",
            slug="same-day",
            is_occasion=False,
            is_active=True,
            sort_order=100,
        )
    else:
        same_day.name = "ارسال روز"
        same_day.slug = "same-day"
        same_day.is_occasion = False
        same_day.is_active = True
        same_day.sort_order = 100
        same_day.save()


class Migration(migrations.Migration):
    dependencies = [
        ("main", "0012_alter_category_cover_image_alter_event_cover_image_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="HeroFont",
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
                    "name",
                    models.CharField(
                        help_text="یک نام واضح بنویس؛ مثلاً «فونت فارسی کمپین نوروز».",
                        max_length=100,
                        unique=True,
                        verbose_name="نام نمایشی فونت",
                    ),
                ),
                (
                    "font_file",
                    models.FileField(
                        help_text="فرمت WOFF2 پیشنهاد می‌شود. فرمت‌های WOFF، TTF و OTF هم پذیرفته می‌شوند. حداکثر حجم فایل ۵ مگابایت است.",
                        upload_to=main.models.hero_font_upload_to,
                        validators=[
                            django.core.validators.FileExtensionValidator(
                                ["woff2", "woff", "ttf", "otf"]
                            ),
                            main.models.validate_hero_font_file_size,
                        ],
                        verbose_name="فایل فونت",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="اگر خاموش شود، Heroهایی که این فونت را انتخاب کرده‌اند بدون خطا با فونت پیش‌فرض نمایش داده می‌شوند.",
                        verbose_name="قابل انتخاب باشد؟",
                    ),
                ),
            ],
            options={
                "verbose_name": "فونت Hero",
                "verbose_name_plural": "فونت‌های Hero",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="category",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                help_text="فقط برای ساخت زیردسته انتخاب شود. مثال: «ماشین عروس» و «دسته‌گل عروس» هر دو والد «عروسی» دارند.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="main.category",
                verbose_name="دسته والد",
            ),
        ),
        migrations.AddField(
            model_name="homeheroslide",
            name="builtin_font",
            field=models.CharField(
                choices=[
                    ("estedad", "استعداد (فارسی)"),
                    ("vazirmatn", "وزیرمتن (فارسی)"),
                    ("cormorant", "Cormorant Garamond (انگلیسی)"),
                    ("jakarta", "Plus Jakarta Sans (انگلیسی)"),
                ],
                default="estedad",
                help_text="اگر فونت آپلودی انتخاب نشود یا در دسترس نباشد، این فونت استفاده می‌شود.",
                max_length=20,
                verbose_name="فونت داخلی",
            ),
        ),
        migrations.AddField(
            model_name="homeheroslide",
            name="body_font_size",
            field=models.PositiveSmallIntegerField(
                default=18,
                help_text="بر حسب پیکسل؛ بازه مجاز ۱۲ تا ۳۲.",
                validators=[
                    django.core.validators.MinValueValidator(12),
                    django.core.validators.MaxValueValidator(32),
                ],
                verbose_name="اندازه توضیح در دسکتاپ",
            ),
        ),
        migrations.AddField(
            model_name="homeheroslide",
            name="content_position",
            field=models.CharField(
                choices=main.models.HERO_POSITION_CHOICES,
                default="bottom-right",
                help_text="جای تقریبی کل بلوک متن روی تصویر دسکتاپ را مشخص می‌کند.",
                max_length=20,
                verbose_name="موقعیت متن در دسکتاپ",
            ),
        ),
        migrations.AddField(
            model_name="homeheroslide",
            name="custom_font",
            field=models.ForeignKey(
                blank=True,
                help_text="اختیاری است. در صورت انتخاب، بر فونت داخلی اولویت دارد.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="home_hero_slides",
                to="main.herofont",
                verbose_name="فونت آپلودی",
            ),
        ),
        migrations.AddField(
            model_name="homeheroslide",
            name="mobile_body_font_size",
            field=models.PositiveSmallIntegerField(
                default=14,
                help_text="بر حسب پیکسل؛ بازه مجاز ۱۲ تا ۲۴.",
                validators=[
                    django.core.validators.MinValueValidator(12),
                    django.core.validators.MaxValueValidator(24),
                ],
                verbose_name="اندازه توضیح در موبایل",
            ),
        ),
        migrations.AddField(
            model_name="homeheroslide",
            name="mobile_content_position",
            field=models.CharField(
                choices=main.models.HERO_POSITION_CHOICES,
                default="bottom-center",
                help_text="موقعیت مستقل متن روی تصویر موبایل؛ برای جلوگیری از پوشاندن سوژه.",
                max_length=20,
                verbose_name="موقعیت متن در موبایل",
            ),
        ),
        migrations.AddField(
            model_name="homeheroslide",
            name="mobile_title_font_size",
            field=models.PositiveSmallIntegerField(
                default=40,
                help_text="بر حسب پیکسل؛ بازه مجاز ۲۲ تا ۷۲.",
                validators=[
                    django.core.validators.MinValueValidator(22),
                    django.core.validators.MaxValueValidator(72),
                ],
                verbose_name="اندازه عنوان در موبایل",
            ),
        ),
        migrations.AddField(
            model_name="homeheroslide",
            name="text_color",
            field=models.CharField(
                default="#FFFFFF",
                help_text="رنگ شش‌رقمی؛ مثل #FFFFFF برای سفید یا #2D2A27 برای قهوه‌ای تیره.",
                max_length=7,
                validators=[main.models.HEX_COLOR_VALIDATOR],
                verbose_name="رنگ متن",
            ),
        ),
        migrations.AddField(
            model_name="homeheroslide",
            name="title_font_size",
            field=models.PositiveSmallIntegerField(
                default=64,
                help_text="بر حسب پیکسل؛ بازه مجاز ۲۸ تا ۱۲۰.",
                validators=[
                    django.core.validators.MinValueValidator(28),
                    django.core.validators.MaxValueValidator(120),
                ],
                verbose_name="اندازه عنوان در دسکتاپ",
            ),
        ),
        migrations.AddField(
            model_name="sitehero",
            name="builtin_font",
            field=models.CharField(
                choices=main.models.HERO_BUILTIN_FONT_CHOICES,
                default="estedad",
                help_text="اگر فونت آپلودی انتخاب نشود یا در دسترس نباشد، این فونت استفاده می‌شود.",
                max_length=20,
                verbose_name="فونت داخلی",
            ),
        ),
        migrations.AddField(
            model_name="sitehero",
            name="body_font_size",
            field=models.PositiveSmallIntegerField(
                default=18,
                help_text="بر حسب پیکسل؛ بازه مجاز ۱۲ تا ۳۲.",
                validators=[
                    django.core.validators.MinValueValidator(12),
                    django.core.validators.MaxValueValidator(32),
                ],
                verbose_name="اندازه توضیح در دسکتاپ",
            ),
        ),
        migrations.AddField(
            model_name="sitehero",
            name="content_position",
            field=models.CharField(
                choices=main.models.HERO_POSITION_CHOICES,
                default="center-left",
                help_text="جای تقریبی کل بلوک متن روی تصویر دسکتاپ را مشخص می‌کند.",
                max_length=20,
                verbose_name="موقعیت متن در دسکتاپ",
            ),
        ),
        migrations.AddField(
            model_name="sitehero",
            name="custom_font",
            field=models.ForeignKey(
                blank=True,
                help_text="اختیاری است. در صورت انتخاب، بر فونت داخلی اولویت دارد.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="site_heroes",
                to="main.herofont",
                verbose_name="فونت آپلودی",
            ),
        ),
        migrations.AddField(
            model_name="sitehero",
            name="mobile_body_font_size",
            field=models.PositiveSmallIntegerField(
                default=14,
                help_text="بر حسب پیکسل؛ بازه مجاز ۱۲ تا ۲۴.",
                validators=[
                    django.core.validators.MinValueValidator(12),
                    django.core.validators.MaxValueValidator(24),
                ],
                verbose_name="اندازه توضیح در موبایل",
            ),
        ),
        migrations.AddField(
            model_name="sitehero",
            name="mobile_content_position",
            field=models.CharField(
                choices=main.models.HERO_POSITION_CHOICES,
                default="bottom-center",
                help_text="موقعیت مستقل متن روی تصویر موبایل؛ برای جلوگیری از پوشاندن سوژه.",
                max_length=20,
                verbose_name="موقعیت متن در موبایل",
            ),
        ),
        migrations.AddField(
            model_name="sitehero",
            name="mobile_title_font_size",
            field=models.PositiveSmallIntegerField(
                default=40,
                help_text="بر حسب پیکسل؛ بازه مجاز ۲۲ تا ۷۲.",
                validators=[
                    django.core.validators.MinValueValidator(22),
                    django.core.validators.MaxValueValidator(72),
                ],
                verbose_name="اندازه عنوان در موبایل",
            ),
        ),
        migrations.AddField(
            model_name="sitehero",
            name="text_color",
            field=models.CharField(
                default="#FFFFFF",
                help_text="رنگ شش‌رقمی؛ مثل #FFFFFF برای سفید یا #2D2A27 برای قهوه‌ای تیره.",
                max_length=7,
                validators=[main.models.HEX_COLOR_VALIDATOR],
                verbose_name="رنگ متن",
            ),
        ),
        migrations.AddField(
            model_name="sitehero",
            name="title_font_size",
            field=models.PositiveSmallIntegerField(
                default=68,
                help_text="بر حسب پیکسل؛ بازه مجاز ۲۸ تا ۱۲۰.",
                validators=[
                    django.core.validators.MinValueValidator(28),
                    django.core.validators.MaxValueValidator(120),
                ],
                verbose_name="اندازه عنوان در دسکتاپ",
            ),
        ),
        migrations.CreateModel(
            name="SameDayFlower",
            fields=[],
            options={
                "verbose_name": "مدیریت ارسال روز",
                "verbose_name_plural": "مدیریت ارسال روز",
                "ordering": ["sort_order", "-updated_at"],
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("main.product",),
        ),
        migrations.RunPython(restore_wedding_categories, migrations.RunPython.noop),
    ]
