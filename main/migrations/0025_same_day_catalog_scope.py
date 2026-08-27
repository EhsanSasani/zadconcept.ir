from django.db import migrations, models
from django.db.models import Q


LEGACY_SAME_DAY_SLUG = "same-day"
LEGACY_SAME_DAY_NAMES = ("ارسال روز", "ارسال فوری")


def migrate_same_day_products(apps, schema_editor):
    Product = apps.get_model("main", "Product")
    Tag = apps.get_model("main", "Tag")
    through = Product.tags.through

    same_day_tags = Tag.objects.filter(
        Q(slug=LEGACY_SAME_DAY_SLUG) | Q(name__in=LEGACY_SAME_DAY_NAMES)
    ).order_by("pk")
    tag_ids = list(same_day_tags.values_list("pk", flat=True))
    if not tag_ids:
        return

    product_ids = list(
        through.objects.filter(tag_id__in=tag_ids)
        .values_list("product_id", flat=True)
        .distinct()
    )
    Product.objects.filter(
        pk__in=product_ids,
        catalog_scope="general",
        category__section="flowers",
    ).update(catalog_scope="same_day")

    # The legacy marker is retired, but retained inactive so this migration is
    # reversible and old database references remain understandable.
    through.objects.filter(tag_id__in=tag_ids).delete()
    same_day_tags.update(is_active=False, is_occasion=False)


def restore_same_day_tag(apps, schema_editor):
    Product = apps.get_model("main", "Product")
    Tag = apps.get_model("main", "Tag")
    through = Product.tags.through

    tag = Tag.objects.filter(slug=LEGACY_SAME_DAY_SLUG).order_by("pk").first()
    if tag is None:
        tag = Tag.objects.filter(name__in=LEGACY_SAME_DAY_NAMES).order_by("pk").first()
    if tag is None:
        tag = Tag.objects.create(
            name="ارسال روز",
            slug=LEGACY_SAME_DAY_SLUG,
            is_active=True,
            is_occasion=False,
            sort_order=100,
        )
    else:
        Tag.objects.filter(pk=tag.pk).update(
            is_active=True,
            is_occasion=False,
        )

    product_ids = list(
        Product.objects.filter(catalog_scope="same_day").values_list(
            "pk", flat=True
        )
    )
    Product.objects.filter(pk__in=product_ids).update(catalog_scope="general")
    through.objects.bulk_create(
        [through(product_id=product_id, tag_id=tag.pk) for product_id in product_ids],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    atomic = True

    dependencies = [
        ("main", "0024_telegram_bot_user"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="product",
            name="product_wedding_scope_state_valid",
        ),
        migrations.AlterField(
            model_name="product",
            name="catalog_scope",
            field=models.CharField(
                choices=[
                    ("general", "کاتالوگ عمومی"),
                    ("same_day", "ارسال روز"),
                    ("wedding", "عروسی"),
                ],
                db_index=True,
                default="general",
                editable=False,
                max_length=16,
                verbose_name="محدوده کاتالوگ",
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="tags",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "مناسبت یا کاربرد محصول؛ مثل تولد، ترحیم، عاشقانه، "
                    "یونیک و ..."
                ),
                related_name="products",
                to="main.tag",
                verbose_name="برچسب‌ها",
            ),
        ),
        migrations.RunPython(
            migrate_same_day_products,
            restore_same_day_tag,
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=(
                    Q(
                        catalog_scope__in=("general", "same_day"),
                        wedding_type="",
                        wedding_needs_review=False,
                    )
                    | Q(
                        catalog_scope="wedding",
                        wedding_type="",
                        wedding_needs_review=True,
                    )
                    | Q(
                        catalog_scope="wedding",
                        wedding_type__in=(
                            "bridal_bouquet",
                            "wedding_car",
                            "proposal_bouquet",
                            "proposal_sweets",
                        ),
                        wedding_needs_review=False,
                    )
                ),
                name="product_wedding_scope_state_valid",
            ),
        ),
    ]
