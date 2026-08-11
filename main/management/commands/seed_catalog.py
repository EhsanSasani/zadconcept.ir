from django.db import transaction

from django.core.management.base import BaseCommand

from main.models import (
    BRIDAL_BOUQUET_CATEGORY_SLUG,
    PROPOSAL_BOUQUET_CATEGORY_SLUG,
    PROPOSAL_SWEETS_CATEGORY_SLUG,
    WEDDING_CAR_CATEGORY_SLUG,
    WEDDING_LEGACY_TAG_SLUGS,
    WEDDING_ROOT_CATEGORY_SLUG,
    Category,
    Product,
    Tag,
)


class Command(BaseCommand):
    help = (
        "Seed/sync ZAD catalog taxonomy without inferring Wedding scope from "
        "product names, slugs, or legacy tags."
    )

    FLOWER_CATEGORIES = [
        {
            "name": "دسته گل",
            "slug": "hand-bouquet",
            "sort_order": 10,
            "legacy_slugs": ["bouquet"],
        },
        {
            "name": "باکس گل",
            "slug": "box",
            "sort_order": 20,
            "legacy_names": ["باکس"],
        },
        {
            "name": "بوکت",
            "slug": "bouquet",
            "sort_order": 30,
        },
        {
            "name": "استند گل",
            "slug": "stand",
            "sort_order": 40,
            "legacy_names": ["استند"],
        },
        {
            "name": "جار گل",
            "slug": "jarl",
            "sort_order": 70,
        },
        {
            "name": "گیاه",
            "slug": "plants",
            "sort_order": 80,
            "legacy_slugs": ["plant"],
        },
    ]

    # The root is a holding category for migrated records that require a human
    # type decision. The four leaf categories are the only publishable Wedding
    # product types.
    WEDDING_CATEGORIES = [
        {
            "section": Category.Section.FLOWERS,
            "name": "عروسی",
            "slug": WEDDING_ROOT_CATEGORY_SLUG,
            "sort_order": 50,
            "legacy_slugs": ["wedding-decoration"],
        },
        {
            "section": Category.Section.FLOWERS,
            "name": "ماشین عروس",
            "slug": WEDDING_CAR_CATEGORY_SLUG,
            "parent_slug": WEDDING_ROOT_CATEGORY_SLUG,
            "sort_order": 10,
        },
        {
            "section": Category.Section.FLOWERS,
            "name": "دسته‌گل عروس",
            "slug": BRIDAL_BOUQUET_CATEGORY_SLUG,
            "parent_slug": WEDDING_ROOT_CATEGORY_SLUG,
            "sort_order": 20,
        },
        {
            "section": Category.Section.FLOWERS,
            "name": "دسته‌گل خواستگاری و بله‌برون",
            "slug": PROPOSAL_BOUQUET_CATEGORY_SLUG,
            "parent_slug": WEDDING_ROOT_CATEGORY_SLUG,
            "sort_order": 30,
        },
        {
            "section": Category.Section.BAKERY,
            "name": "شیرینی خواستگاری و بله‌برون",
            "slug": PROPOSAL_SWEETS_CATEGORY_SLUG,
            "sort_order": 10,
        },
    ]

    OTHER_CATEGORIES = [
        {
            "section": Category.Section.BAKERY,
            "name": "کیک تولد",
            "slug": "birthday-cakes",
            "sort_order": 10,
        },
        {
            "section": Category.Section.BAKERY,
            "name": "کوکی",
            "slug": "cookies",
            "sort_order": 20,
        },
        {
            "section": Category.Section.GIFTS,
            "name": "شمع",
            "slug": "candles",
            "sort_order": 10,
        },
        {
            "section": Category.Section.GIFTS,
            "name": "سفال",
            "slug": "ceramic",
            "sort_order": 20,
        },
        {
            "section": Category.Section.GIFTS,
            "name": "سایر",
            "slug": "others",
            "sort_order": 30,
        },
    ]

    TAGS = [
        {
            "name": "تولد",
            "slug": "birthday",
            "sort_order": 10,
            "legacy_slugs": ["birthday"],
        },
        {
            "name": "عاشقانه",
            "slug": "romantic",
            "sort_order": 20,
            "legacy_slugs": ["romantic"],
        },
        {
            "name": "یونیک",
            "slug": "unique",
            "sort_order": 30,
            "legacy_slugs": ["special"],
            "legacy_names": ["خاص"],
        },
        {
            "name": "تبریک",
            "slug": "congratulation",
            "sort_order": 40,
            "legacy_slugs": ["congratulations"],
        },
        {
            "name": "معذرت خواهی",
            "slug": "apology",
            "sort_order": 50,
            "is_occasion": False,
            "legacy_slugs": ["apology"],
            "legacy_names": ["عذرخواهی"],
        },
        {
            "name": "ترحیم",
            "slug": "condolence",
            "sort_order": 60,
            "legacy_slugs": ["condolence", "sympathy"],
            "legacy_names": ["تسلیت"],
        },
        {
            "name": "دیدار رسمی",
            "slug": "formal-visit",
            "sort_order": 70,
        },
        {
            "name": "بی‌بهانه",
            "slug": "no-occasion",
            "sort_order": 90,
            "legacy_slugs": ["no-occasion"],
        },
        {
            "name": "ارسال روز",
            "slug": "same-day",
            "sort_order": 100,
            "is_occasion": False,
            "legacy_slugs": ["same-day"],
            "legacy_names": ["ارسال فوری"],
        },
    ]

    PROTECTED_WEDDING_TAGS = [
        {
            "name": "خواستگاری",
            "slug": "proposal",
            "sort_order": 70,
        },
        {
            "name": "بله برون",
            "slug": "engagement",
            "sort_order": 80,
        },
        {
            "name": "عروسی",
            "slug": "wedding",
            "sort_order": 85,
        },
    ]

    def handle(self, *args, **options):
        self.stdout.write("شروع همگام‌سازی کاتالوگ زاد...")

        with transaction.atomic():
            for item in self.FLOWER_CATEGORIES:
                self.sync_category(
                    section=Category.Section.FLOWERS,
                    name=item["name"],
                    slug=item["slug"],
                    sort_order=item["sort_order"],
                    legacy_slugs=item.get("legacy_slugs", []),
                    legacy_names=item.get("legacy_names", []),
                )

            for item in self.WEDDING_CATEGORIES + self.OTHER_CATEGORIES:
                self.sync_category(
                    section=item["section"],
                    name=item["name"],
                    slug=item["slug"],
                    sort_order=item["sort_order"],
                    parent_slug=item.get("parent_slug"),
                    legacy_slugs=item.get("legacy_slugs", []),
                    legacy_names=item.get("legacy_names", []),
                )

            self.deactivate_legacy_flower_category(
                "basket",
                "سبد گل قدیمی غیرفعال شد.",
            )

            # Clear all Wedding M2M relations before any legacy general-tag
            # merge can encounter them through the runtime m2m guard.
            self.reconcile_wedding_products()

            for item in self.TAGS:
                self.sync_tag(
                    name=item["name"],
                    slug=item["slug"],
                    sort_order=item["sort_order"],
                    is_occasion=item.get("is_occasion", True),
                    is_active=True,
                    legacy_slugs=item.get("legacy_slugs", []),
                    legacy_names=item.get("legacy_names", []),
                )

            for item in self.PROTECTED_WEDDING_TAGS:
                self.sync_tag(
                    name=item["name"],
                    slug=item["slug"],
                    sort_order=item["sort_order"],
                    is_occasion=False,
                    is_active=False,
                )

            # Keep this explicit even if a duplicate/legacy tag was merged by
            # sync_tag above.
            Tag.objects.filter(slug__in=WEDDING_LEGACY_TAG_SLUGS).update(
                is_active=False,
                is_occasion=False,
            )

        self.stdout.write(
            self.style.SUCCESS("کاتالوگ زاد با موفقیت همگام‌سازی شد.")
        )

    def sync_category(
        self,
        *,
        section,
        name,
        slug,
        sort_order,
        parent_slug=None,
        legacy_slugs=None,
        legacy_names=None,
    ):
        legacy_slugs = legacy_slugs or []
        legacy_names = legacy_names or []

        category = self.find_category(section, slug, name, legacy_slugs, legacy_names)
        target = Category.objects.filter(section=section, slug=slug).first()

        if category and target and category.pk != target.pk:
            moved = Product.objects.filter(category=category).update(category=target)
            category.is_active = False
            category.slug = f"{category.slug}-legacy-{category.pk}"
            category.name = f"{category.name} قدیمی"
            category.save(update_fields=["is_active", "slug", "name", "updated_at"])
            category = target
            self.stdout.write(
                self.style.WARNING(
                    f"{moved} محصول از دسته قدیمی به {target} منتقل شد."
                )
            )

        if category:
            created = False
        else:
            category = Category(section=section, slug=slug)
            created = True

        category.name = name
        category.slug = slug
        category.section = section
        category.parent = (
            Category.objects.get(section=section, slug=parent_slug)
            if parent_slug
            else None
        )
        category.is_active = True
        category.sort_order = sort_order
        category.save()

        status = "ساخته شد" if created else "به‌روزرسانی شد"
        self.stdout.write(self.style.SUCCESS(f"{category} - {status}"))
        return category

    def reconcile_wedding_products(self):
        """Normalize only products already carrying the explicit Wedding scope."""

        category_by_type = {
            wedding_type: Category.objects.get(section=section, slug=slug)
            for wedding_type, (section, slug) in Product.WEDDING_CATEGORY_MAP.items()
        }
        wedding_root = Category.objects.get(
            section=Category.Section.FLOWERS,
            slug=WEDDING_ROOT_CATEGORY_SLUG,
        )

        reconciled = 0
        review_count = 0
        cleared_tag_count = 0
        wedding_products = list(
            Product.objects.for_weddings().prefetch_related("tags").order_by("pk")
        )

        for product in wedding_products:
            if product.tags.exists():
                product.tags.clear()
                cleared_tag_count += 1

            target = category_by_type.get(product.wedding_type)
            if product.wedding_needs_review or target is None:
                Product.objects.filter(pk=product.pk).update(
                    category=wedding_root,
                    wedding_type="",
                    wedding_needs_review=True,
                )
                review_count += 1
            else:
                Product.objects.filter(pk=product.pk).update(
                    category=target,
                    wedding_needs_review=False,
                )
            reconciled += 1

        self.stdout.write(
            "محصولات Wedding همگام‌شده: "
            f"{reconciled} | نیازمند بررسی: {review_count} | "
            f"روابط Tag پاک‌شده: {cleared_tag_count}"
        )

    def find_category(self, section, slug, name, legacy_slugs, legacy_names):
        lookups = [
            {"section": section, "slug": slug},
            {"section": section, "name": name},
        ]
        lookups += [
            {"section": section, "slug": legacy_slug}
            for legacy_slug in legacy_slugs
        ]
        lookups += [
            {"section": section, "name": legacy_name}
            for legacy_name in legacy_names
        ]

        for lookup in lookups:
            category = Category.objects.filter(**lookup).order_by("id").first()
            if category:
                return category
        return None

    def deactivate_legacy_flower_category(self, slug, message):
        category = Category.objects.filter(
            section=Category.Section.FLOWERS,
            slug=slug,
            is_active=True,
        ).first()
        if not category:
            return

        if Product.objects.filter(category=category).exists():
            self.stdout.write(
                self.style.WARNING(f"{category} محصول دارد؛ غیرفعال نشد.")
            )
            return

        category.is_active = False
        category.save(update_fields=["is_active", "updated_at"])
        self.stdout.write(self.style.WARNING(message))

    def sync_tag(
        self,
        *,
        name,
        slug,
        sort_order,
        is_occasion=True,
        is_active=True,
        legacy_slugs=None,
        legacy_names=None,
    ):
        legacy_slugs = legacy_slugs or []
        legacy_names = legacy_names or []

        tag = self.find_tag(slug, name, legacy_slugs, legacy_names)
        target = Tag.objects.filter(slug=slug).first()

        if tag and target and tag.pk != target.pk:
            if slug not in WEDDING_LEGACY_TAG_SLUGS:
                for product in tag.products.all():
                    product.tags.add(target)
            tag.is_active = False
            tag.slug = f"{tag.slug}-legacy-{tag.pk}"
            tag.name = f"{tag.name} قدیمی"
            tag.save(update_fields=["is_active", "slug", "name", "updated_at"])
            tag = target
            self.stdout.write(
                self.style.WARNING(f"برچسب قدیمی در {target} ادغام شد.")
            )

        if tag:
            created = False
        else:
            tag = Tag(slug=slug)
            created = True

        tag.name = name
        tag.slug = slug
        tag.is_occasion = is_occasion
        tag.is_active = is_active
        tag.sort_order = sort_order
        tag.save()

        status = "ساخته شد" if created else "به‌روزرسانی شد"
        self.stdout.write(self.style.SUCCESS(f"{tag} - {status}"))
        return tag

    def find_tag(self, slug, name, legacy_slugs, legacy_names):
        lookups = [{"slug": slug}, {"name": name}]
        lookups += [{"slug": legacy_slug} for legacy_slug in legacy_slugs]
        lookups += [{"name": legacy_name} for legacy_name in legacy_names]

        for lookup in lookups:
            tag = Tag.objects.filter(**lookup).order_by("id").first()
            if tag:
                return tag
        return None
