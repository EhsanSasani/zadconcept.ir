from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

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
    WeddingMigrationSnapshot,
)


class Command(BaseCommand):
    help = (
        "Read-only audit of Wedding catalog scope, types, taxonomy, legacy "
        "migration snapshots, tags, and public-catalog isolation."
    )

    EXPECTED_CATEGORIES = (
        (
            "wedding_root",
            Category.Section.FLOWERS,
            WEDDING_ROOT_CATEGORY_SLUG,
            "عروسی",
            None,
        ),
        (
            Product.WeddingType.BRIDAL_BOUQUET,
            Category.Section.FLOWERS,
            BRIDAL_BOUQUET_CATEGORY_SLUG,
            "دسته‌گل عروس",
            WEDDING_ROOT_CATEGORY_SLUG,
        ),
        (
            Product.WeddingType.WEDDING_CAR,
            Category.Section.FLOWERS,
            WEDDING_CAR_CATEGORY_SLUG,
            "ماشین عروس",
            WEDDING_ROOT_CATEGORY_SLUG,
        ),
        (
            Product.WeddingType.PROPOSAL_BOUQUET,
            Category.Section.FLOWERS,
            PROPOSAL_BOUQUET_CATEGORY_SLUG,
            "دسته‌گل خواستگاری و بله‌برون",
            WEDDING_ROOT_CATEGORY_SLUG,
        ),
        (
            Product.WeddingType.PROPOSAL_SWEETS,
            Category.Section.BAKERY,
            PROPOSAL_SWEETS_CATEGORY_SLUG,
            "شیرینی خواستگاری و بله‌برون",
            None,
        ),
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help=(
                "Exit non-zero when review items, catalog leaks, invalid "
                "scope/type mappings, or protected-taxonomy violations exist."
            ),
        )

    def handle(self, *args, **options):
        # Windows may expose a legacy Persian code page that cannot encode all
        # Unicode characters used in real taxonomy names. Prefer UTF-8 when the
        # underlying console stream supports reconfiguration; captured test
        # streams (StringIO) intentionally remain untouched.
        for output in (self.stdout, self.stderr):
            stream = getattr(output, "_out", None)
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")

        self.stdout.write("=== WEDDING CATALOG AUDIT ===")
        self.stdout.write("READ_ONLY=yes")

        wedding_products = Product.objects.for_weddings()
        review_products = self.product_list(
            wedding_products.filter(wedding_needs_review=True)
        )

        self.stdout.write(
            "SUMMARY "
            f"total_wedding={wedding_products.count()} "
            f"needs_review={len(review_products)} "
            f"snapshots={WeddingMigrationSnapshot.objects.count()}"
        )
        for wedding_type, _label in Product.WeddingType.choices:
            count = wedding_products.filter(wedding_type=wedding_type).count()
            self.stdout.write(f"TYPE {wedding_type}={count}")

        snapshots = list(
            WeddingMigrationSnapshot.objects.select_related("product").order_by(
                "product_id"
            )
        )
        migrated_snapshot_count = sum(
            1 for snapshot in snapshots if snapshot.migrated_to_wedding
        )
        self.stdout.write(
            "SNAPSHOTS "
            f"total={len(snapshots)} "
            f"migrated_to_wedding={migrated_snapshot_count} "
            f"cleanup_only={len(snapshots) - migrated_snapshot_count}"
        )
        for reason, count in sorted(
            Counter(snapshot.migration_reason for snapshot in snapshots).items()
        ):
            self.stdout.write(f"SNAPSHOT_REASON {reason}={count}")
        self.report_snapshots(snapshots)

        protected_category_ids = Category.objects.for_weddings().values_list(
            "pk",
            flat=True,
        )
        # Start from the unfiltered concrete manager. Using
        # ``for_general_catalog()`` here would hide the exact protected-category
        # corruption this command is responsible for detecting.
        non_wedding_products = Product.objects.filter(
            catalog_scope__in=(
                Product.CatalogScope.GENERAL,
                Product.CatalogScope.SAME_DAY,
            )
        )

        wedding_general_taxonomy = self.product_list(
            wedding_products.exclude(category_id__in=protected_category_ids)
        )
        wedding_with_tags = self.product_list(
            wedding_products.filter(tags__isnull=False).distinct()
        )
        non_wedding_protected_category = self.product_list(
            non_wedding_products.filter(category_id__in=protected_category_ids)
        )
        non_wedding_protected_tag = self.product_list(
            non_wedding_products.filter(
                tags__slug__in=WEDDING_LEGACY_TAG_SLUGS
            ).distinct()
        )

        valid_typed_ids = Product.objects.valid_weddings().values_list(
            "pk",
            flat=True,
        )
        typed_mapping_mismatch = self.product_list(
            wedding_products.filter(wedding_needs_review=False).exclude(
                pk__in=valid_typed_ids
            )
        )
        scope_state_mismatch = self.product_list(
            Product.objects.filter(
                Q(
                    catalog_scope__in=(
                        Product.CatalogScope.GENERAL,
                        Product.CatalogScope.SAME_DAY,
                    ),
                )
                & (
                    ~Q(wedding_type="")
                    | Q(wedding_needs_review=True)
                )
                | Q(
                    catalog_scope=Product.CatalogScope.WEDDING,
                    wedding_needs_review=True,
                )
                & (
                    ~Q(wedding_type="")
                    | ~Q(
                        category__section=Category.Section.FLOWERS,
                        category__slug=WEDDING_ROOT_CATEGORY_SLUG,
                    )
                )
                | ~Q(
                    catalog_scope__in=(
                        Product.CatalogScope.GENERAL,
                        Product.CatalogScope.SAME_DAY,
                        Product.CatalogScope.WEDDING,
                    )
                )
            )
        )

        taxonomy_issues = self.taxonomy_issues()
        protected_tag_issues = self.protected_tag_issues()

        product_checks = (
            ("NEEDS_REVIEW", review_products),
            ("WEDDING_GENERAL_TAXONOMY", wedding_general_taxonomy),
            ("WEDDING_WITH_TAGS", wedding_with_tags),
            ("NON_WEDDING_PROTECTED_CATEGORY", non_wedding_protected_category),
            ("NON_WEDDING_PROTECTED_TAG", non_wedding_protected_tag),
            ("TYPED_MAPPING_MISMATCH", typed_mapping_mismatch),
            ("SCOPE_STATE_MISMATCH", scope_state_mismatch),
        )

        failing_checks = []
        for check_name, products in product_checks:
            self.report_products(check_name, products)
            if products:
                failing_checks.append(check_name)

        self.report_messages("TAXONOMY_CONFIGURATION", taxonomy_issues)
        if taxonomy_issues:
            failing_checks.append("TAXONOMY_CONFIGURATION")

        self.report_messages("PROTECTED_TAG_STATE", protected_tag_issues)
        if protected_tag_issues:
            failing_checks.append("PROTECTED_TAG_STATE")

        if failing_checks:
            names = ",".join(failing_checks)
            self.stdout.write(
                self.style.WARNING(
                    f"RESULT issues={len(failing_checks)} checks={names}"
                )
            )
            self.stdout.write("Audit finished. No data changed.")
            if options["strict"]:
                raise CommandError(
                    "Wedding audit failed with "
                    f"{len(failing_checks)} failing check(s): {names}"
                )
            return

        self.stdout.write(self.style.SUCCESS("RESULT ok issues=0"))
        self.stdout.write("Audit finished. No data changed.")

    @staticmethod
    def product_list(queryset):
        return list(
            queryset.select_related("category", "category__parent")
            .prefetch_related("tags")
            .order_by("pk")
        )

    def report_products(self, check_name, products):
        self.stdout.write(f"[{check_name}] count={len(products)}")
        for product in products:
            self.stdout.write(f"  {self.product_line(product)}")

    def report_snapshots(self, snapshots):
        self.stdout.write(f"[LEGACY_SNAPSHOTS] count={len(snapshots)}")
        for snapshot in snapshots:
            product = snapshot.product
            tag_ids = ",".join(str(tag_id) for tag_id in snapshot.original_tag_ids)
            self.stdout.write(
                "  "
                f"ID={product.pk} code={product.product_code or '-'} "
                f"name={self.clean_value(product.name)} slug={product.slug or '-'} "
                f"reason={snapshot.migration_reason} "
                f"migrated_to_wedding={self.yes_no(snapshot.migrated_to_wedding)} "
                f"original_category_id={snapshot.original_category_id} "
                f"original_tag_ids={tag_ids or '-'} "
                f"original_scope={snapshot.original_catalog_scope or '-'} "
                f"original_type={snapshot.original_wedding_type or '-'} "
                "original_review="
                f"{self.yes_no(snapshot.original_wedding_needs_review)} "
                f"original_wedding_sort_order={snapshot.original_wedding_sort_order}"
            )

    def report_messages(self, check_name, messages):
        self.stdout.write(f"[{check_name}] count={len(messages)}")
        for message in messages:
            self.stdout.write(f"  {message}")

    def taxonomy_issues(self):
        issues = []
        for key, section, slug, expected_name, expected_parent_slug in (
            self.EXPECTED_CATEGORIES
        ):
            category = (
                Category.objects.filter(section=section, slug=slug)
                .select_related("parent")
                .first()
            )
            if category is None:
                issues.append(f"{key}: missing category {section}/{slug}")
                continue
            if not category.is_active:
                issues.append(f"{key}: category ID={category.pk} is inactive")
            if category.name != expected_name:
                issues.append(
                    f"{key}: category ID={category.pk} name={category.name!r} "
                    f"expected={expected_name!r}"
                )
            parent_slug = category.parent.slug if category.parent_id else None
            if parent_slug != expected_parent_slug:
                issues.append(
                    f"{key}: category ID={category.pk} parent={parent_slug or '-'} "
                    f"expected={expected_parent_slug or '-'}"
                )
        return issues

    @staticmethod
    def protected_tag_issues():
        issues = []
        for tag in Tag.objects.filter(
            slug__in=WEDDING_LEGACY_TAG_SLUGS
        ).order_by("slug"):
            if tag.is_active or tag.is_occasion:
                issues.append(
                    f"Tag ID={tag.pk} slug={tag.slug} "
                    f"is_active={tag.is_active} is_occasion={tag.is_occasion}"
                )
        return issues

    @staticmethod
    def clean_value(value):
        value = " ".join(str(value or "").split())
        return value or "-"

    @staticmethod
    def yes_no(value):
        return "yes" if value else "no"

    def product_line(self, product):
        category = product.category
        parent = (
            f"{category.parent_id}:{category.parent.slug}"
            if category.parent_id
            else "-"
        )
        tags = ",".join(
            f"{tag.pk}:{tag.slug}" for tag in sorted(product.tags.all(), key=lambda t: t.pk)
        )
        return (
            f"ID={product.pk} code={product.product_code or '-'} "
            f"name={self.clean_value(product.name)} slug={product.slug or '-'} "
            f"scope={product.catalog_scope or '-'} "
            f"type={product.wedding_type or '-'} "
            f"review={self.yes_no(product.wedding_needs_review)} "
            f"category={category.pk}:{category.section}/{category.slug} "
            f"category_name={self.clean_value(category.name)} "
            f"parent={parent} tags={tags or '-'}"
        )
