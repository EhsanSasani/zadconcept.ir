from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from .management.commands.apply_catalog_hotfix_20260811 import (
    BRIDAL_PRIORITY_CODES,
    DELETE_CODES,
    FORMAL_VISIT_CODES,
    JUST_BECAUSE_CODES,
    PROPOSAL_COLLECTION_CODES,
)
from .management.commands.seed_catalog import Command as SeedCatalogCommand
from .models import (
    Category,
    Product,
    PROPOSAL_COLLECTION_TAG_SLUG,
    Tag,
)


def create_product(code, category, *, name=None, **extra):
    defaults = {
        "name": name or f"Hotfix product {code}",
        "product_code": code,
        "slug": f"hotfix-product-{code}",
        "category": category,
        "publish_status": Product.PublishStatus.PUBLISHED,
        "is_active": True,
    }
    defaults.update(extra)
    return Product.objects.create(**defaults)


def create_wedding_taxonomy():
    root, _ = Category.objects.update_or_create(
        slug="wedding",
        section=Category.Section.FLOWERS,
        defaults={
            "name": "عروسی",
            "parent": None,
            "is_active": True,
            "sort_order": 50,
        },
    )
    bridal, _ = Category.objects.update_or_create(
        slug="bridal-bouquet",
        section=Category.Section.FLOWERS,
        defaults={
            "name": "دسته‌گل عروس",
            "parent": root,
            "is_active": True,
            "sort_order": 20,
        },
    )
    proposal, _ = Category.objects.update_or_create(
        slug="proposal-bale-boroon-bouquet",
        section=Category.Section.FLOWERS,
        defaults={
            "name": "دسته‌گل خواستگاری و بله‌برون",
            "parent": root,
            "is_active": True,
            "sort_order": 30,
        },
    )
    return root, bridal, proposal


class ProposalCollectionFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hand_bouquet = Category.objects.create(
            name="دسته گل",
            slug="hand-bouquet",
            section=Category.Section.FLOWERS,
            is_active=True,
            sort_order=10,
        )
        cls.box = Category.objects.create(
            name="باکس گل",
            slug="box",
            section=Category.Section.FLOWERS,
            is_active=True,
            sort_order=20,
        )
        _, _, proposal_category = create_wedding_taxonomy()
        cls.birthday = Tag.objects.create(
            name="تولد",
            slug="birthday",
            is_occasion=True,
            is_active=True,
        )
        cls.selection = Tag.objects.create(
            name="کالکشن خواستگاری (سیستمی)",
            slug=PROPOSAL_COLLECTION_TAG_SLUG,
            is_occasion=False,
            is_active=False,
        )
        cls.hand_product = create_product(
            "9901",
            cls.hand_bouquet,
            name="Proposal selected hand bouquet",
        )
        cls.box_product = create_product(
            "9902",
            cls.box,
            name="Proposal selected box",
        )
        cls.unselected = create_product(
            "9903",
            cls.hand_bouquet,
            name="General flower outside proposal",
        )
        cls.dedicated = create_product(
            "9904",
            proposal_category,
            name="Dedicated proposal wedding product",
            catalog_scope=Product.CatalogScope.WEDDING,
            wedding_type=Product.WeddingType.PROPOSAL_BOUQUET,
        )
        cls.hand_product.tags.add(cls.birthday, cls.selection)
        cls.box_product.tags.add(cls.birthday, cls.selection)
        cls.unselected.tags.add(cls.birthday)

    def test_selected_general_products_render_in_both_original_and_proposal_pages(self):
        proposal_url = reverse("wedding_collection", args=["proposal-bouquets"])
        response = self.client.get(proposal_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["products"],
            [self.dedicated, self.hand_product, self.box_product],
        )
        self.assertContains(response, self.hand_product.product_code)
        self.assertContains(response, self.box_product.product_code)
        self.assertNotContains(response, self.unselected.product_code)
        self.assertEqual(
            [item["label"] for item in response.context["filter_links"]],
            ["All", "دسته گل", "باکس گل"],
        )
        self.assertContains(response, "?category=hand-bouquet")

        original = self.client.get(
            reverse("flower_subcategory", args=[self.hand_bouquet.slug])
        )
        self.assertContains(original, self.hand_product.product_code)
        detail = self.client.get(self.hand_product.get_absolute_url())
        self.assertContains(detail, self.birthday.name)
        self.assertNotContains(detail, self.selection.name)
        self.assertEqual(
            set(self.hand_product.tags.values_list("slug", flat=True)),
            {"birthday", PROPOSAL_COLLECTION_TAG_SLUG},
        )

    def test_proposal_filter_uses_original_packaging_category(self):
        response = self.client.get(
            reverse("wedding_collection", args=["proposal-bouquets"]),
            {"category": self.hand_bouquet.slug},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["products"], [self.hand_product])
        self.assertContains(response, self.hand_product.product_code)
        self.assertNotContains(response, self.box_product.product_code)
        self.assertNotContains(response, self.dedicated.product_code)
        self.assertEqual(response.context["selected_category"], self.hand_bouquet)

    def test_selection_does_not_leak_to_other_wedding_collections(self):
        response = self.client.get(
            reverse("wedding_collection", args=["bridal-bouquets"])
        )

        self.assertNotContains(response, self.hand_product.product_code)
        self.assertNotContains(response, self.box_product.product_code)


class CatalogCurationCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hand_bouquet = Category.objects.create(
            name="دسته گل",
            slug="hand-bouquet",
            section=Category.Section.FLOWERS,
            is_active=True,
            sort_order=10,
        )
        cls.box = Category.objects.create(
            name="باکس گل",
            slug="box",
            section=Category.Section.FLOWERS,
            is_active=True,
            sort_order=20,
        )
        _, cls.bridal_category, _ = create_wedding_taxonomy()
        cls.previous_tag = Tag.objects.create(
            name="تولد",
            slug="birthday",
            is_occasion=True,
            is_active=True,
            sort_order=10,
        )
        cls.apology = Tag.objects.create(
            name="معذرت خواهی",
            slug="apology",
            is_occasion=True,
            is_active=True,
            sort_order=50,
        )
        cls.just_because = Tag.objects.create(
            name="بدون مناسبت",
            slug="no-occasion",
            is_occasion=True,
            is_active=True,
            sort_order=90,
        )

        general_codes = (
            set(PROPOSAL_COLLECTION_CODES)
            | set(DELETE_CODES)
            | set(FORMAL_VISIT_CODES)
            | set(JUST_BECAUSE_CODES)
        )
        cls.general_products = {}
        for index, code in enumerate(sorted(general_codes)):
            category = cls.hand_bouquet if index % 2 == 0 else cls.box
            product = create_product(code, category)
            cls.general_products[code] = product

        additive_codes = (
            set(PROPOSAL_COLLECTION_CODES)
            | set(FORMAL_VISIT_CODES)
            | set(JUST_BECAUSE_CODES)
        )
        for code in additive_codes:
            cls.general_products[code].tags.add(cls.previous_tag)

        cls.bridal_products = {}
        for code in BRIDAL_PRIORITY_CODES:
            cls.bridal_products[code] = create_product(
                code,
                cls.bridal_category,
                catalog_scope=Product.CatalogScope.WEDDING,
                wedding_type=Product.WeddingType.BRIDAL_BOUQUET,
            )
        cls.other_bridal = create_product(
            "9000",
            cls.bridal_category,
            name="Other bridal product",
            catalog_scope=Product.CatalogScope.WEDDING,
            wedding_type=Product.WeddingType.BRIDAL_BOUQUET,
        )

    def test_dry_run_is_read_only_and_apply_is_additive_and_complete(self):
        dry_output = StringIO()
        call_command("apply_catalog_hotfix_20260811", stdout=dry_output)

        self.assertIn("DRY-RUN only", dry_output.getvalue())
        self.assertFalse(
            Tag.objects.filter(slug=PROPOSAL_COLLECTION_TAG_SLUG).exists()
        )
        self.assertFalse(Tag.objects.filter(slug="formal-visit").exists())
        self.assertEqual(
            Product.objects.filter(product_code__in=DELETE_CODES).count(),
            len(DELETE_CODES),
        )
        self.apology.refresh_from_db()
        self.assertTrue(self.apology.is_occasion)

        apply_output = StringIO()
        call_command(
            "apply_catalog_hotfix_20260811",
            apply=True,
            stdout=apply_output,
        )

        self.assertIn("Catalog hotfix applied successfully", apply_output.getvalue())
        proposal_tag = Tag.objects.get(slug=PROPOSAL_COLLECTION_TAG_SLUG)
        formal_tag = Tag.objects.get(slug="formal-visit")
        just_because_tag = Tag.objects.get(slug="no-occasion")

        self.assertFalse(proposal_tag.is_active)
        self.assertFalse(proposal_tag.is_occasion)
        self.assertEqual(formal_tag.name, "دیدار رسمی")
        self.assertTrue(formal_tag.is_occasion)
        self.assertEqual(just_because_tag.name, "بی‌بهانه")
        self.assertTrue(just_because_tag.is_occasion)

        for code in PROPOSAL_COLLECTION_CODES:
            slugs = set(
                Product.objects.get(product_code=code).tags.values_list(
                    "slug",
                    flat=True,
                )
            )
            self.assertIn("birthday", slugs)
            self.assertIn(PROPOSAL_COLLECTION_TAG_SLUG, slugs)

        for code in FORMAL_VISIT_CODES:
            slugs = set(
                Product.objects.get(product_code=code).tags.values_list(
                    "slug",
                    flat=True,
                )
            )
            self.assertIn("birthday", slugs)
            self.assertIn("formal-visit", slugs)

        for code in JUST_BECAUSE_CODES:
            slugs = set(
                Product.objects.get(product_code=code).tags.values_list(
                    "slug",
                    flat=True,
                )
            )
            self.assertIn("birthday", slugs)
            self.assertIn("no-occasion", slugs)

        self.assertFalse(Product.objects.filter(product_code__in=DELETE_CODES).exists())
        self.apology.refresh_from_db()
        self.assertFalse(self.apology.is_occasion)

        occasions = self.client.get(reverse("occasions"))
        self.assertContains(occasions, "دیدار رسمی")
        self.assertContains(occasions, "بی‌بهانه")
        self.assertNotContains(occasions, "معذرت خواهی")
        self.assertEqual(
            self.client.get(reverse("occasion_detail", args=["apology"])).status_code,
            404,
        )
        formal_visit = self.client.get(
            reverse("occasion_detail", args=["formal-visit"])
        )
        self.assertEqual(formal_visit.status_code, 200)
        self.assertEqual(
            {product.product_code for product in formal_visit.context["products"]},
            set(FORMAL_VISIT_CODES),
        )
        just_because = self.client.get(
            reverse("occasion_detail", args=["no-occasion"])
        )
        self.assertEqual(just_because.status_code, 200)
        self.assertEqual(
            {product.product_code for product in just_because.context["products"]},
            set(JUST_BECAUSE_CODES),
        )

        bridal_order = list(
            Product.objects.valid_weddings()
            .published()
            .filter(wedding_type=Product.WeddingType.BRIDAL_BOUQUET)
            .order_by(
                "wedding_sort_order",
                "sort_order",
                "-created_at",
                "id",
            )
            .values_list("product_code", flat=True)
        )
        self.assertEqual(
            bridal_order[: len(BRIDAL_PRIORITY_CODES)],
            list(BRIDAL_PRIORITY_CODES),
        )
        self.assertEqual(bridal_order[-1], self.other_bridal.product_code)

    def test_missing_code_aborts_before_any_write(self):
        Product.objects.filter(product_code=DELETE_CODES[0]).delete()

        with self.assertRaises(CommandError):
            call_command("apply_catalog_hotfix_20260811", apply=True)

        self.assertFalse(Tag.objects.filter(slug="formal-visit").exists())
        self.assertFalse(
            Tag.objects.filter(slug=PROPOSAL_COLLECTION_TAG_SLUG).exists()
        )
        self.apology.refresh_from_db()
        self.assertTrue(self.apology.is_occasion)


class CatalogSeedPolicyTests(TestCase):
    def test_seed_policy_keeps_hotfix_occasion_state(self):
        tags = {item["slug"]: item for item in SeedCatalogCommand.TAGS}

        self.assertFalse(tags["apology"]["is_occasion"])
        self.assertEqual(tags["formal-visit"]["name"], "دیدار رسمی")
        self.assertEqual(tags["no-occasion"]["name"], "بی‌بهانه")
