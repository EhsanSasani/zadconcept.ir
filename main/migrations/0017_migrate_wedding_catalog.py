from django.db import migrations
from django.db.models import Q


AMBIGUOUS_LEGACY_CODES = {
    "0527",
    "0528",
    "0529",
    "0531",
    "0533",
    "0534",
    "0536",
    "0537",
    "0538",
    "0539",
    "0540",
    "0541",
    "0553",
    "0554",
    "0555",
    "0556",
    "0557",
    "0559",
    "0562",
    "0563",
}

PROTECTED_TAG_SLUGS = ("wedding", "proposal", "engagement")


def _ensure_category(
    Category,
    TaxonomySnapshot,
    *,
    section,
    name,
    slug,
    parent=None,
    sort_order=0,
):
    snapshot_key = f"category:{section}:{slug}"
    category = Category.objects.filter(section=section, slug=slug).first()
    if category is None:
        category = Category.objects.filter(section=section, name=name).first()
    existed_before = category is not None
    original_values = {}
    if existed_before:
        original_values = {
            "name": category.name,
            "slug": category.slug,
            "section": category.section,
            "parent_id": category.parent_id,
            "is_active": category.is_active,
            "sort_order": category.sort_order,
        }
    if category is None:
        category = Category(section=section, slug=slug)

    category.name = name
    category.slug = slug
    category.section = section
    category.parent_id = parent.pk if parent else None
    category.is_active = True
    category.sort_order = sort_order
    category.save()
    TaxonomySnapshot.objects.get_or_create(
        key=snapshot_key,
        defaults={
            "object_kind": "category",
            "object_id": category.pk,
            "existed_before": existed_before,
            "original_values": original_values,
        },
    )
    return category


def migrate_wedding_catalog(apps, schema_editor):
    Category = apps.get_model("main", "Category")
    Product = apps.get_model("main", "Product")
    Snapshot = apps.get_model("main", "WeddingMigrationSnapshot")
    Tag = apps.get_model("main", "Tag")
    TaxonomySnapshot = apps.get_model(
        "main", "WeddingTaxonomyMigrationSnapshot"
    )

    wedding_root = _ensure_category(
        Category,
        TaxonomySnapshot,
        section="flowers",
        name="عروسی",
        slug="wedding",
        sort_order=50,
    )
    wedding_car = _ensure_category(
        Category,
        TaxonomySnapshot,
        section="flowers",
        name="ماشین عروس",
        slug="wedding-car",
        parent=wedding_root,
        sort_order=10,
    )
    bridal_bouquet = _ensure_category(
        Category,
        TaxonomySnapshot,
        section="flowers",
        name="دسته‌گل عروس",
        slug="bridal-bouquet",
        parent=wedding_root,
        sort_order=20,
    )
    proposal_bouquet = _ensure_category(
        Category,
        TaxonomySnapshot,
        section="flowers",
        name="دسته‌گل خواستگاری و بله‌برون",
        slug="proposal-bale-boroon-bouquet",
        parent=wedding_root,
        sort_order=30,
    )
    proposal_sweets = _ensure_category(
        Category,
        TaxonomySnapshot,
        section="bakery",
        name="شیرینی خواستگاری و بله‌برون",
        slug="proposal-bale-boroon-sweets",
        sort_order=10,
    )

    category_by_type = {
        "bridal_bouquet": bridal_bouquet,
        "wedding_car": wedding_car,
        "proposal_bouquet": proposal_bouquet,
        "proposal_sweets": proposal_sweets,
    }

    protected_tags = list(Tag.objects.filter(slug__in=PROTECTED_TAG_SLUGS))
    for tag in protected_tags:
        TaxonomySnapshot.objects.get_or_create(
            key=f"tag:{tag.slug}",
            defaults={
                "object_kind": "tag",
                "object_id": tag.pk,
                "existed_before": True,
                "original_values": {
                    "is_active": tag.is_active,
                    "is_occasion": tag.is_occasion,
                },
            },
        )
    protected_tag_ids = {tag.pk for tag in protected_tags}
    proposal_tag_ids = {
        tag.pk for tag in protected_tags if tag.slug in {"proposal", "engagement"}
    }
    wedding_tag_ids = {tag.pk for tag in protected_tags if tag.slug == "wedding"}

    products = list(
        Product.objects.select_related("category").prefetch_related("tags").order_by("pk")
    )
    TaxonomySnapshot.objects.get_or_create(
        key="product:canonical-url-state",
        defaults={
            "object_kind": "product_urls",
            "object_id": None,
            "existed_before": True,
            "original_values": {
                str(product.pk): {
                    "canonical_section": product.canonical_section,
                    "canonical_category_slug": product.canonical_category_slug,
                }
                for product in products
            },
        },
    )
    candidates = {}

    for product in products:
        category = product.category
        tag_ids = {tag.pk for tag in product.tags.all()}

        # Preserve the full pre-migration detail URL even when taxonomy changes.
        Product.objects.filter(pk=product.pk).update(
            canonical_section=category.section,
            canonical_category_slug=category.slug,
        )

        if (
            product.product_code in AMBIGUOUS_LEGACY_CODES
            and category.section == "flowers"
            and category.slug == "bridal-bouquet"
        ):
            candidates[product.pk] = (None, "legacy_0013_ambiguous")
        elif category.section == "flowers" and category.slug == "wedding-car":
            candidates[product.pk] = ("wedding_car", "wedding_car_category")
        elif category.section == "flowers" and category.slug in {
            "bridal-bouquet",
            "wedding-bouquet",
        }:
            candidates[product.pk] = ("bridal_bouquet", "bridal_category")
        elif (
            category.section == "flowers"
            and category.slug == "hand-bouquet"
            and tag_ids.intersection(proposal_tag_ids)
        ):
            candidates[product.pk] = ("proposal_bouquet", "proposal_bouquet_tag")
        elif (
            category.section == "bakery"
            and tag_ids.intersection(proposal_tag_ids)
        ):
            candidates[product.pk] = ("proposal_sweets", "proposal_sweets_tag")
        elif (
            category.section == "flowers"
            and category.slug in {"wedding", "wedding-decoration"}
        ) or tag_ids.intersection(wedding_tag_ids):
            candidates[product.pk] = (None, "legacy_wedding_untyped")

    for product in products:
        tag_ids = [tag.pk for tag in product.tags.all()]
        candidate = candidates.get(product.pk)
        has_protected_tag = bool(set(tag_ids).intersection(protected_tag_ids))
        if candidate is None and not has_protected_tag:
            continue

        wedding_type, reason = candidate or (None, "legacy_tag_cleanup")
        Snapshot.objects.update_or_create(
            product_id=product.pk,
            defaults={
                "original_category_id": product.category_id,
                "original_tag_ids": tag_ids,
                "original_catalog_scope": product.catalog_scope,
                "original_wedding_type": product.wedding_type,
                "original_wedding_needs_review": product.wedding_needs_review,
                "original_wedding_sort_order": product.wedding_sort_order,
                "migration_reason": reason,
                "migrated_to_wedding": candidate is not None,
            },
        )

        if candidate is None:
            product.tags.remove(*protected_tag_ids)
            continue

        # Wedding products do not keep public Tag/Same-Day relationships. The
        # exact M2M state is retained in WeddingMigrationSnapshot for rollback.
        product.tags.clear()
        if wedding_type:
            Product.objects.filter(pk=product.pk).update(
                category_id=category_by_type[wedding_type].pk,
                catalog_scope="wedding",
                wedding_type=wedding_type,
                wedding_needs_review=False,
                wedding_sort_order=product.sort_order,
            )
        else:
            Product.objects.filter(pk=product.pk).update(
                category_id=wedding_root.pk,
                catalog_scope="wedding",
                wedding_type="",
                wedding_needs_review=True,
                wedding_sort_order=product.sort_order,
            )

    Tag.objects.filter(slug__in=PROTECTED_TAG_SLUGS).update(
        is_active=False,
        is_occasion=False,
    )


def restore_pre_wedding_catalog(apps, schema_editor):
    Category = apps.get_model("main", "Category")
    Product = apps.get_model("main", "Product")
    Snapshot = apps.get_model("main", "WeddingMigrationSnapshot")
    Tag = apps.get_model("main", "Tag")
    TaxonomySnapshot = apps.get_model(
        "main", "WeddingTaxonomyMigrationSnapshot"
    )

    for snapshot in Snapshot.objects.select_related("product").order_by("product_id"):
        Product.objects.filter(pk=snapshot.product_id).update(
            category_id=snapshot.original_category_id,
            catalog_scope=snapshot.original_catalog_scope,
            wedding_type=snapshot.original_wedding_type,
            wedding_needs_review=snapshot.original_wedding_needs_review,
            wedding_sort_order=snapshot.original_wedding_sort_order,
        )
        product = Product.objects.get(pk=snapshot.product_id)
        existing_tag_ids = list(
            Tag.objects.filter(pk__in=snapshot.original_tag_ids).values_list(
                "pk", flat=True
            )
        )
        product.tags.set(existing_tag_ids)

    canonical_snapshot = TaxonomySnapshot.objects.filter(
        key="product:canonical-url-state"
    ).first()
    if canonical_snapshot:
        for product_id, values in canonical_snapshot.original_values.items():
            Product.objects.filter(pk=product_id).update(
                canonical_section=values.get("canonical_section", ""),
                canonical_category_slug=values.get("canonical_category_slug", ""),
            )

    for taxonomy_snapshot in TaxonomySnapshot.objects.filter(object_kind="tag"):
        values = taxonomy_snapshot.original_values
        Tag.objects.filter(pk=taxonomy_snapshot.object_id).update(
            is_active=values.get("is_active", True),
            is_occasion=values.get("is_occasion", False),
        )

    category_snapshots = TaxonomySnapshot.objects.filter(
        object_kind="category"
    ).order_by("key")
    for taxonomy_snapshot in category_snapshots:
        if not taxonomy_snapshot.existed_before:
            Category.objects.filter(pk=taxonomy_snapshot.object_id).update(
                is_active=False
            )
            continue
        values = taxonomy_snapshot.original_values
        Category.objects.filter(pk=taxonomy_snapshot.object_id).update(
            name=values["name"],
            slug=values["slug"],
            section=values["section"],
            parent_id=values.get("parent_id"),
            is_active=values["is_active"],
            sort_order=values["sort_order"],
        )

    Snapshot.objects.all().delete()
    TaxonomySnapshot.objects.all().delete()


class Migration(migrations.Migration):
    atomic = True

    dependencies = [
        ("main", "0016_wedding_schema"),
    ]

    operations = [
        migrations.RunPython(
            migrate_wedding_catalog,
            restore_pre_wedding_catalog,
        ),
    ]
