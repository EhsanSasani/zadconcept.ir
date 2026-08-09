import base64
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from .admin import WeddingProductAdminForm
from .models import (
    BakeryItem,
    Category,
    Flower,
    Product,
    ProductImage,
    SameDayFlower,
    Tag,
    WeddingCollectionContent,
    WeddingPageContent,
    WeddingProduct,
)
from .sitemaps import CategorySitemap


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def ensure_wedding_taxonomy():
    root, _ = Category.objects.update_or_create(
        section=Category.Section.FLOWERS,
        slug="wedding",
        defaults={
            "name": "عروسی",
            "parent": None,
            "is_active": True,
            "sort_order": 50,
        },
    )
    bridal, _ = Category.objects.update_or_create(
        section=Category.Section.FLOWERS,
        slug="bridal-bouquet",
        defaults={
            "name": "دسته‌گل عروس",
            "parent": root,
            "is_active": True,
            "sort_order": 20,
        },
    )
    car, _ = Category.objects.update_or_create(
        section=Category.Section.FLOWERS,
        slug="wedding-car",
        defaults={
            "name": "ماشین عروس",
            "parent": root,
            "is_active": True,
            "sort_order": 10,
        },
    )
    proposal_bouquet, _ = Category.objects.update_or_create(
        section=Category.Section.FLOWERS,
        slug="proposal-bale-boroon-bouquet",
        defaults={
            "name": "دسته‌گل خواستگاری و بله‌برون",
            "parent": root,
            "is_active": True,
            "sort_order": 30,
        },
    )
    proposal_sweets, _ = Category.objects.update_or_create(
        section=Category.Section.BAKERY,
        slug="proposal-bale-boroon-sweets",
        defaults={
            "name": "شیرینی خواستگاری و بله‌برون",
            "parent": None,
            "is_active": True,
            "sort_order": 10,
        },
    )
    return {
        "root": root,
        Product.WeddingType.BRIDAL_BOUQUET: bridal,
        Product.WeddingType.WEDDING_CAR: car,
        Product.WeddingType.PROPOSAL_BOUQUET: proposal_bouquet,
        Product.WeddingType.PROPOSAL_SWEETS: proposal_sweets,
    }


def create_wedding_product(name, wedding_type, category, **extra):
    defaults = {
        "catalog_scope": Product.CatalogScope.WEDDING,
        "wedding_type": wedding_type,
        "category": category,
        "publish_status": Product.PublishStatus.PUBLISHED,
        "is_active": True,
    }
    defaults.update(extra)
    return Product.objects.create(name=name, **defaults)


class WeddingCatalogIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.taxonomy = ensure_wedding_taxonomy()
        cls.general_flower_category = Category.objects.create(
            name="WTest General Flowers",
            slug="wtest-general-flowers",
            section=Category.Section.FLOWERS,
        )
        cls.general_bakery_category = Category.objects.create(
            name="WTest General Bakery",
            slug="wtest-general-bakery",
            section=Category.Section.BAKERY,
        )
        cls.same_day, _ = Tag.objects.update_or_create(
            slug="same-day",
            defaults={
                "name": "ارسال روز",
                "is_active": True,
                "is_occasion": False,
            },
        )
        cls.birthday, _ = Tag.objects.update_or_create(
            slug="birthday",
            defaults={
                "name": "تولد",
                "is_active": True,
                "is_occasion": True,
            },
        )
        cls.general_flower = Product.objects.create(
            name="WTEST GENERAL FLOWER",
            category=cls.general_flower_category,
            publish_status=Product.PublishStatus.PUBLISHED,
            featured=True,
        )
        cls.general_flower.tags.add(cls.birthday)
        cls.general_same_day = Product.objects.create(
            name="WTEST GENERAL SAME DAY",
            category=cls.general_flower_category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        cls.general_same_day.tags.add(cls.same_day)
        cls.general_bakery = Product.objects.create(
            name="WTEST GENERAL BAKERY",
            category=cls.general_bakery_category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

        cls.bridal = create_wedding_product(
            "WTEST BRIDAL",
            Product.WeddingType.BRIDAL_BOUQUET,
            cls.taxonomy[Product.WeddingType.BRIDAL_BOUQUET],
            featured=True,
            wedding_sort_order=4,
        )
        cls.car = create_wedding_product(
            "WTEST WEDDING CAR",
            Product.WeddingType.WEDDING_CAR,
            cls.taxonomy[Product.WeddingType.WEDDING_CAR],
            featured=True,
            wedding_sort_order=3,
        )
        cls.proposal_bouquet = create_wedding_product(
            "WTEST PROPOSAL BOUQUET",
            Product.WeddingType.PROPOSAL_BOUQUET,
            cls.taxonomy[Product.WeddingType.PROPOSAL_BOUQUET],
            featured=True,
            wedding_sort_order=2,
        )
        cls.proposal_sweets = create_wedding_product(
            "WTEST PROPOSAL SWEETS",
            Product.WeddingType.PROPOSAL_SWEETS,
            cls.taxonomy[Product.WeddingType.PROPOSAL_SWEETS],
            featured=True,
            wedding_sort_order=1,
        )
        cls.wedding_products = (
            cls.bridal,
            cls.car,
            cls.proposal_bouquet,
            cls.proposal_sweets,
        )

        review_source = Product.objects.create(
            name="WTEST REVIEW HIDDEN",
            category=cls.general_flower_category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        Product.objects.filter(pk=review_source.pk).update(
            category=cls.taxonomy["root"],
            catalog_scope=Product.CatalogScope.WEDDING,
            wedding_type="",
            wedding_needs_review=True,
        )
        review_source.refresh_from_db()
        cls.review_product = review_source

    def test_general_flower_and_same_day_keep_their_public_surfaces(self):
        directory = self.client.get(reverse("flowers"))
        all_flowers = self.client.get(reverse("flowers_all"))
        category = self.client.get(
            reverse("flower_subcategory", args=[self.general_flower_category.slug])
        )
        same_day = self.client.get(reverse("flowers_same_day"))

        self.assertContains(directory, self.general_flower_category.name)
        self.assertContains(all_flowers, self.general_flower.name)
        self.assertContains(all_flowers, self.general_same_day.name)
        self.assertContains(category, self.general_flower.name)
        self.assertContains(category, self.general_same_day.name)
        self.assertContains(same_day, self.general_same_day.name)
        self.assertNotContains(same_day, self.general_flower.name)

    def test_landing_links_to_four_collections_and_products_render_only_inside_them(self):
        landing = self.client.get(reverse("weddings"))
        self.assertEqual(landing.status_code, 200)

        expected = {
            "bridal-bouquets": self.bridal,
            "wedding-cars": self.car,
            "proposal-bouquets": self.proposal_bouquet,
            "proposal-sweets": self.proposal_sweets,
        }
        self.assertEqual(len(landing.context["wedding_collections"]), 4)
        for slug, product in expected.items():
            url = reverse("wedding_collection", args=[slug])
            self.assertContains(landing, f'href="{url}"')
            self.assertNotContains(landing, product.name)

            collection = self.client.get(url)
            self.assertEqual(collection.status_code, 200)
            self.assertIn(product, collection.context["products"])
            self.assertContains(collection, product.name)
            for other in self.wedding_products:
                if other.pk != product.pk:
                    self.assertNotContains(collection, other.name)

        self.assertNotContains(landing, self.review_product.name)
        self.assertEqual(
            self.client.get(reverse("wedding_collection", args=["unknown"])).status_code,
            404,
        )

    def test_wedding_products_do_not_leak_to_any_general_surface(self):
        paths = (
            reverse("index"),
            reverse("flowers"),
            reverse("flowers_all"),
            reverse("flowers_same_day"),
            reverse("bakery"),
            reverse("bakery_all"),
            reverse("occasion_detail", args=[self.birthday.slug]),
        )
        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            for product in self.wedding_products:
                self.assertNotContains(response, product.name, msg_prefix=path)
            self.assertNotContains(response, self.review_product.name, msg_prefix=path)

    def test_raw_same_day_or_general_tag_tampering_fails_closed(self):
        through = Product.tags.through
        through.objects.create(product_id=self.bridal.pk, tag_id=self.same_day.pk)
        through.objects.create(product_id=self.car.pk, tag_id=self.birthday.pk)

        valid_ids = set(Product.objects.valid_weddings().values_list("pk", flat=True))
        self.assertNotIn(self.bridal.pk, valid_ids)
        self.assertNotIn(self.car.pk, valid_ids)
        landing = self.client.get(reverse("weddings"))
        bridal_collection = self.client.get(
            reverse("wedding_collection", args=["bridal-bouquets"])
        )
        car_collection = self.client.get(
            reverse("wedding_collection", args=["wedding-cars"])
        )
        same_day = self.client.get(reverse("flowers_same_day"))
        occasion = self.client.get(
            reverse("occasion_detail", args=[self.birthday.slug])
        )
        for response in (landing, bridal_collection, car_collection, same_day, occasion):
            self.assertNotContains(response, self.bridal.name)
            self.assertNotContains(response, self.car.name)

    def test_wedding_and_general_related_products_never_cross(self):
        wedding_response = self.client.get(self.bridal.get_absolute_url())
        general_response = self.client.get(self.general_flower.get_absolute_url())

        self.assertEqual(wedding_response.status_code, 200)
        self.assertEqual(general_response.status_code, 200)
        self.assertTrue(wedding_response.context["similar_items"])
        self.assertTrue(
            all(item.is_wedding for item in wedding_response.context["similar_items"])
        )
        self.assertTrue(
            all(
                not item.is_wedding
                for item in general_response.context["similar_items"]
            )
        )
        self.assertContains(wedding_response, f'href="{reverse("weddings")}"')
        self.assertIn(
            reverse("weddings"),
            [crumb["url"] for crumb in wedding_response.context["breadcrumbs"]],
        )

    def test_landing_managed_seo_canonical_and_empty_groups_are_safe(self):
        WeddingPageContent.objects.create(
            hero_title="WTEST MANAGED WEDDING HERO",
            seo_title="WTEST MANAGED SEO TITLE",
            meta_description="WTEST managed wedding description",
            contact_url="tel:+985100000000",
            telegram_url="https://t.me/zad_test",
        )
        response = self.client.get(reverse("weddings"))

        self.assertEqual(
            response.context["canonical_url"],
            "https://www.zadconcept.ir/weddings/",
        )
        self.assertContains(response, "WTEST MANAGED SEO TITLE")
        self.assertContains(response, "WTEST managed wedding description")
        self.assertNotContains(response, 'href="tel:+985100000000"')
        self.assertNotContains(response, "PERSONAL COORDINATION")

        Product.objects.for_weddings().update(
            publish_status=Product.PublishStatus.DRAFT
        )
        empty = self.client.get(reverse("weddings"))
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(len(empty.context["wedding_collections"]), 4)
        self.assertTrue(
            all(item["product_count"] == 0 for item in empty.context["wedding_collections"])
        )
        empty_collection = self.client.get(
            reverse("wedding_collection", args=["bridal-bouquets"])
        )
        self.assertEqual(empty_collection.status_code, 200)
        self.assertEqual(empty_collection.context["products"], [])

    def test_collection_transfer_title_and_text_only_intro_are_preserved(self):
        content = WeddingCollectionContent.objects.get(
            collection_key="proposal-bouquets"
        )
        self.assertEqual(content.hero_title, "گل‌های خواستگاری و بله‌برون")

        content.hero_image = "weddings/collections/proposal-desktop.webp"
        content.hero_mobile_image = "weddings/collections/proposal-mobile.webp"
        content.save(update_fields=("hero_image", "hero_mobile_image", "updated_at"))

        response = self.client.get(
            reverse("wedding_collection", args=["proposal-bouquets"])
        )
        self.assertContains(response, "گل‌های خواستگاری و بله‌برون")
        self.assertNotContains(response, "wedding-collection-intro--with-media")
        self.assertNotContains(response, 'class="wedding-collection-intro__media"')

    def test_all_legacy_taxonomy_urls_are_permanent_redirects(self):
        paths = (
            "/flowers/wedding/",
            "/flowers/wedding-car/",
            "/flowers/bridal-bouquet/",
            "/flowers/proposal-bale-boroon-bouquet/",
            "/flowers/wedding-bouquet/",
            "/flowers/wedding-decoration/",
            "/flowers/proposal/",
            "/flowers/engagement/",
            "/bakery/proposal-bale-boroon-sweets/",
            "/bakery/wedding/",
            "/bakery/proposal/",
            "/bakery/engagement/",
            "/flowers/occasion/wedding/",
            "/flowers/occasion/proposal/",
            "/flowers/occasion/engagement/",
            "/occasions/wedding/",
            "/occasions/proposal/",
            "/occasions/engagement/",
        )
        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 301, path)
            self.assertEqual(response.headers["Location"], reverse("weddings"), path)

    def test_current_detail_url_is_immutable_when_taxonomy_moves(self):
        original_url = self.general_flower.get_absolute_url()
        Product.objects.filter(pk=self.general_flower.pk).update(
            category=self.general_bakery_category
        )
        self.general_flower.refresh_from_db()

        self.assertEqual(self.general_flower.get_absolute_url(), original_url)
        self.assertEqual(self.client.get(original_url).status_code, 200)


class WeddingInvariantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.taxonomy = ensure_wedding_taxonomy()
        cls.general_flower = Category.objects.create(
            name="WInvariant Flowers",
            slug="winvariant-flowers",
            section=Category.Section.FLOWERS,
        )
        cls.general_bakery = Category.objects.create(
            name="WInvariant Bakery",
            slug="winvariant-bakery",
            section=Category.Section.BAKERY,
        )
        cls.same_day, _ = Tag.objects.update_or_create(
            slug="same-day",
            defaults={
                "name": "ارسال روز",
                "is_active": True,
                "is_occasion": False,
            },
        )

    def test_default_manager_is_unfiltered_but_proxy_managers_are_isolated(self):
        general = Product.objects.create(
            name="WInvariant General",
            category=self.general_flower,
        )
        wedding = create_wedding_product(
            "WInvariant Wedding",
            Product.WeddingType.BRIDAL_BOUQUET,
            self.taxonomy[Product.WeddingType.BRIDAL_BOUQUET],
        )

        self.assertIn(general, Product.objects.all())
        self.assertIn(wedding, Product.objects.all())
        self.assertIn(general.pk, Flower.objects.values_list("pk", flat=True))
        self.assertNotIn(wedding.pk, Flower.objects.values_list("pk", flat=True))
        self.assertIn(wedding.pk, WeddingProduct.objects.values_list("pk", flat=True))
        self.assertNotIn(general.pk, WeddingProduct.objects.values_list("pk", flat=True))

    def test_general_product_cannot_use_protected_wedding_category(self):
        with self.assertRaises(ValidationError):
            Product.objects.create(
                name="WInvariant Bad General",
                category=self.taxonomy[Product.WeddingType.BRIDAL_BOUQUET],
            )

    def test_wedding_type_section_and_category_mismatches_are_rejected(self):
        invalid = (
            (
                Product.WeddingType.PROPOSAL_SWEETS,
                self.taxonomy[Product.WeddingType.BRIDAL_BOUQUET],
            ),
            (Product.WeddingType.BRIDAL_BOUQUET, self.general_bakery),
            (Product.WeddingType.WEDDING_CAR, self.general_flower),
        )
        for wedding_type, category in invalid:
            with self.subTest(wedding_type=wedding_type, category=category.slug):
                with self.assertRaises(ValidationError):
                    create_wedding_product(
                        f"WInvariant Invalid {wedding_type}",
                        wedding_type,
                        category,
                    )

    def test_new_untyped_wedding_and_same_day_wedding_are_rejected(self):
        with self.assertRaises(ValidationError):
            Product.objects.create(
                name="WInvariant Untyped",
                category=self.taxonomy["root"],
                catalog_scope=Product.CatalogScope.WEDDING,
                wedding_needs_review=True,
            )

        wedding = create_wedding_product(
            "WInvariant No Same Day",
            Product.WeddingType.WEDDING_CAR,
            self.taxonomy[Product.WeddingType.WEDDING_CAR],
        )
        with self.assertRaises(ValidationError):
            wedding.tags.add(self.same_day)

    def test_database_constraint_rejects_impossible_scope_state(self):
        product = Product.objects.create(
            name="WInvariant Constraint",
            category=self.general_flower,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.filter(pk=product.pk).update(
                catalog_scope=Product.CatalogScope.GENERAL,
                wedding_type=Product.WeddingType.BRIDAL_BOUQUET,
            )

    def test_wedding_page_singleton_and_link_validation(self):
        first = WeddingPageContent.objects.create(hero_title="First")
        second = WeddingPageContent.objects.create(hero_title="Second")
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(WeddingPageContent.current(), second)

        with self.assertRaises(ValidationError):
            WeddingPageContent.objects.create(contact_url="javascript:alert(1)")
        with self.assertRaises(ValidationError):
            WeddingPageContent.objects.create(telegram_url="ftp://example.com/file")


class WeddingAdminIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.taxonomy = ensure_wedding_taxonomy()
        cls.general_category = Category.objects.create(
            name="WAdmin General Flowers",
            slug="wadmin-general-flowers",
            section=Category.Section.FLOWERS,
        )
        cls.general = Product.objects.create(
            name="WADMIN GENERAL PRODUCT",
            category=cls.general_category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        cls.wedding = create_wedding_product(
            "WADMIN WEDDING PRODUCT",
            Product.WeddingType.BRIDAL_BOUQUET,
            cls.taxonomy[Product.WeddingType.BRIDAL_BOUQUET],
        )
        cls.user = get_user_model().objects.create_superuser(
            username="wedding-admin-test",
            email="wedding-admin@example.invalid",
            password="test-password",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_general_and_wedding_changelists_are_mutually_exclusive(self):
        general_response = self.client.get(reverse("admin:main_flower_changelist"))
        wedding_response = self.client.get(
            reverse("admin:main_weddingproduct_changelist")
        )

        self.assertContains(general_response, self.general.name)
        self.assertNotContains(general_response, self.wedding.name)
        self.assertContains(wedding_response, self.wedding.name)
        self.assertNotContains(wedding_response, self.general.name)

    def test_legacy_wedding_categories_are_protected_end_to_end(self):
        legacy_categories = [
            Category.objects.create(
                name=f"WADMIN LEGACY {slug}",
                slug=slug,
                section=Category.Section.FLOWERS,
            )
            for slug in ("wedding-bouquet", "wedding-decoration")
        ]

        general_ids = set(
            Category.objects.for_general_catalog().values_list("pk", flat=True)
        )
        wedding_ids = set(Category.objects.for_weddings().values_list("pk", flat=True))
        sitemap_ids = {category.pk for category in CategorySitemap().items()}
        admin_response = self.client.get(reverse("admin:main_category_changelist"))

        for category in legacy_categories:
            self.assertTrue(category.is_wedding_category)
            self.assertNotIn(category.pk, general_ids)
            self.assertIn(category.pk, wedding_ids)
            self.assertNotIn(category.pk, sitemap_ids)
            self.assertNotContains(admin_response, category.name)

            with self.assertRaises(ValidationError):
                Product.objects.create(
                    name=f"WADMIN REJECT {category.slug}",
                    category=category,
                    publish_status=Product.PublishStatus.PUBLISHED,
                )

            tampered = Product.objects.create(
                name=f"WADMIN RAW {category.slug}",
                category=self.general_category,
                publish_status=Product.PublishStatus.PUBLISHED,
            )
            Product.objects.filter(pk=tampered.pk).update(category=category)
            self.assertFalse(
                Product.objects.for_general_catalog().filter(pk=tampered.pk).exists()
            )
            self.assertFalse(
                Product.objects.publicly_indexable().filter(pk=tampered.pk).exists()
            )

    def test_general_choices_and_product_image_choices_hide_wedding(self):
        request = RequestFactory().get(reverse("admin:main_flower_add"))
        request.user = self.user
        form_class = admin.site._registry[Flower].get_form(request)
        form = form_class()
        self.assertNotIn(
            self.taxonomy[Product.WeddingType.BRIDAL_BOUQUET],
            form.fields["category"].queryset,
        )
        self.assertFalse(
            form.fields["tags"].queryset.filter(
                slug__in=("wedding", "proposal", "engagement")
            ).exists()
        )

        response = self.client.get(reverse("admin:main_productimage_add"))
        products = response.context["adminform"].form.fields["product"].queryset
        self.assertIn(self.general, products)
        self.assertNotIn(self.wedding, products)

    def test_general_admin_cannot_open_or_post_wedding_product(self):
        direct_change = self.client.get(
            reverse("admin:main_flower_change", args=[self.wedding.pk])
        )
        self.assertNotEqual(direct_change.status_code, 200)

        response = self.client.post(
            reverse("admin:main_flower_add"),
            {
                "name": "WADMIN TAMPERED PRODUCT",
                "category": self.taxonomy[
                    Product.WeddingType.BRIDAL_BOUQUET
                ].pk,
                "pricing_type": Product.PricingType.INQUIRY,
                "stock_status": Product.StockStatus.IN_STOCK,
                "publish_status": Product.PublishStatus.PUBLISHED,
                "is_active": "on",
                "sort_order": 0,
                "gallery_images-TOTAL_FORMS": 0,
                "gallery_images-INITIAL_FORMS": 0,
                "gallery_images-MIN_NUM_FORMS": 0,
                "gallery_images-MAX_NUM_FORMS": 1000,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name="WADMIN TAMPERED PRODUCT").exists())

    def test_wedding_form_maps_type_to_scope_and_category_server_side(self):
        form = WeddingProductAdminForm(
            data={
                "name": "WADMIN CREATED PROPOSAL SWEETS",
                "pricing_type": Product.PricingType.INQUIRY,
                "price": "",
                "price_usd": "",
                "stock_status": Product.StockStatus.IN_STOCK,
                "publish_status": Product.PublishStatus.PUBLISHED,
                "is_active": True,
                "wedding_type": Product.WeddingType.PROPOSAL_SWEETS,
                "wedding_sort_order": 7,
                "description": "",
                "slug": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        self.assertEqual(product.catalog_scope, Product.CatalogScope.WEDDING)
        self.assertEqual(product.wedding_type, Product.WeddingType.PROPOSAL_SWEETS)
        self.assertEqual(
            product.category,
            self.taxonomy[Product.WeddingType.PROPOSAL_SWEETS],
        )
        self.assertEqual(product.wedding_sort_order, 7)
        self.assertFalse(product.tags.exists())

    def test_view_only_user_has_no_mutating_actions(self):
        viewer = get_user_model().objects.create_user(
            username="wedding-viewer-test",
            password="test-password",
            is_staff=True,
        )
        viewer.user_permissions.add(
            Permission.objects.get(codename="view_weddingproduct")
        )
        request = RequestFactory().get(reverse("admin:main_weddingproduct_changelist"))
        request.user = viewer
        model_admin = admin.site._registry[WeddingProduct]

        actions = model_admin.get_actions(request)
        self.assertEqual(actions, {})


class WeddingAuditCommandTests(TestCase):
    def setUp(self):
        self.taxonomy = ensure_wedding_taxonomy()

    def make_audit_clean(self):
        Product.objects.filter(
            catalog_scope=Product.CatalogScope.WEDDING,
            wedding_needs_review=True,
        ).update(
            category=self.taxonomy[Product.WeddingType.BRIDAL_BOUQUET],
            wedding_type=Product.WeddingType.BRIDAL_BOUQUET,
            wedding_needs_review=False,
        )
        Tag.objects.filter(slug__in=("wedding", "proposal", "engagement")).update(
            is_active=False,
            is_occasion=False,
        )

    def test_audit_is_read_only_and_reports_review_rows(self):
        before = list(
            Product.objects.order_by("pk").values_list(
                "pk", "catalog_scope", "wedding_type", "wedding_needs_review"
            )
        )
        stdout = StringIO()
        call_command("audit_weddings", stdout=stdout)
        after = list(
            Product.objects.order_by("pk").values_list(
                "pk", "catalog_scope", "wedding_type", "wedding_needs_review"
            )
        )

        self.assertEqual(before, after)
        self.assertIn("=== WEDDING CATALOG AUDIT ===", stdout.getvalue())
        self.assertIn("READ_ONLY=yes", stdout.getvalue())
        self.assertIn("[NEEDS_REVIEW]", stdout.getvalue())

    def test_strict_detects_raw_general_product_in_protected_category(self):
        self.make_audit_clean()
        general_category = Category.objects.create(
            name="WAudit General",
            slug="waudit-general",
            section=Category.Section.FLOWERS,
        )
        product = Product.objects.create(name="WAUDIT TAMPER", category=general_category)
        Product.objects.filter(pk=product.pk).update(
            category=self.taxonomy[Product.WeddingType.BRIDAL_BOUQUET]
        )
        stdout = StringIO()

        with self.assertRaises(CommandError):
            call_command("audit_weddings", strict=True, stdout=stdout)
        self.assertIn("[GENERAL_PROTECTED_CATEGORY] count=1", stdout.getvalue())
        self.assertIn(product.product_code, stdout.getvalue())

    def test_strict_passes_when_all_checks_are_clean(self):
        self.make_audit_clean()
        stdout = StringIO()
        call_command("audit_weddings", strict=True, stdout=stdout)
        self.assertIn("RESULT ok issues=0", stdout.getvalue())


class WeddingImportCommandTests(TestCase):
    def setUp(self):
        self.taxonomy = ensure_wedding_taxonomy()
        Category.objects.update_or_create(
            section=Category.Section.FLOWERS,
            slug="hand-bouquet",
            defaults={"name": "دسته گل", "is_active": True},
        )
        Category.objects.update_or_create(
            section=Category.Section.FLOWERS,
            slug="box",
            defaults={"name": "باکس", "is_active": True},
        )

    def test_proposal_code_requires_a_compatible_folder(self):
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as media_dir:
            source = Path(source_dir)
            (source / "box").mkdir()
            (source / "box" / "k.jpg").write_bytes(TINY_PNG)
            before = Product.objects.count()
            stderr = StringIO()
            with override_settings(MEDIA_ROOT=media_dir):
                call_command("import_flash_products", source, stderr=stderr)

        self.assertEqual(Product.objects.count(), before)
        self.assertIn("only valid inside 'daste gol'", stderr.getvalue())

    def test_hand_bouquet_proposal_import_is_exclusive_and_tag_free(self):
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as media_dir:
            source = Path(source_dir)
            (source / "daste gol").mkdir()
            (source / "daste gol" / "k.jpg").write_bytes(TINY_PNG)
            with override_settings(MEDIA_ROOT=media_dir):
                call_command("import_flash_products", source)

        product = Product.objects.order_by("-pk").first()
        self.assertEqual(product.catalog_scope, Product.CatalogScope.WEDDING)
        self.assertEqual(product.wedding_type, Product.WeddingType.PROPOSAL_BOUQUET)
        self.assertEqual(product.category, self.taxonomy[Product.WeddingType.PROPOSAL_BOUQUET])
        self.assertFalse(product.tags.exists())


class WeddingDataMigrationTests(TransactionTestCase):
    migrate_from = ("main", "0015_normalize_global_hero_targets")
    migrate_to = ("main", "0017_migrate_wedding_catalog")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        CategoryV15 = old_apps.get_model("main", "Category")
        ProductV15 = old_apps.get_model("main", "Product")
        ProductImageV15 = old_apps.get_model("main", "ProductImage")
        TagV15 = old_apps.get_model("main", "Tag")

        category, _ = CategoryV15.objects.get_or_create(
            section="flowers",
            slug="hand-bouquet",
            defaults={"name": "Migration Hand Bouquet", "is_active": True},
        )
        proposal, _ = TagV15.objects.get_or_create(
            slug="proposal",
            defaults={
                "name": "Migration Proposal",
                "is_active": True,
                "is_occasion": True,
            },
        )
        product = ProductV15.objects.create(
            name="Migration Identity Product",
            product_code="MIG-W-9001",
            slug="migration-identity-product",
            category=category,
            cover_image="products/covers/migration-original.webp",
            pricing_type="fixed",
            price=987654,
            publish_status="published",
            stock_status="in_stock",
            is_active=True,
        )
        product.tags.add(proposal)
        gallery = ProductImageV15.objects.create(
            product=product,
            image="products/gallery/migration-original.webp",
            alt_text="Migration gallery",
            ordering=2,
        )
        self.identity = {
            "pk": product.pk,
            "code": product.product_code,
            "slug": product.slug,
            "cover": product.cover_image.name,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
            "gallery_pk": gallery.pk,
            "gallery": gallery.image.name,
            "proposal_pk": proposal.pk,
            "category_pk": category.pk,
        }

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_forward_and_reverse_preserve_product_and_media_identity(self):
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state([self.migrate_to]).apps
        ProductV17 = apps.get_model("main", "Product")
        ProductImageV17 = apps.get_model("main", "ProductImage")
        product = ProductV17.objects.get(pk=self.identity["pk"])
        gallery = ProductImageV17.objects.get(pk=self.identity["gallery_pk"])

        self.assertEqual(product.product_code, self.identity["code"])
        self.assertEqual(product.slug, self.identity["slug"])
        self.assertEqual(product.cover_image.name, self.identity["cover"])
        self.assertEqual(product.created_at, self.identity["created_at"])
        self.assertEqual(product.updated_at, self.identity["updated_at"])
        self.assertEqual(gallery.image.name, self.identity["gallery"])
        self.assertEqual(product.catalog_scope, "wedding")
        self.assertEqual(product.wedding_type, "proposal_bouquet")
        self.assertEqual(product.canonical_section, "flowers")
        self.assertEqual(product.canonical_category_slug, "hand-bouquet")
        self.assertFalse(product.tags.exists())

        executor = MigrationExecutor(connection)
        executor.migrate([("main", "0016_wedding_schema")])
        reverse_apps = executor.loader.project_state(
            [("main", "0016_wedding_schema")]
        ).apps
        ReversedProduct = reverse_apps.get_model("main", "Product")
        reversed_product = ReversedProduct.objects.get(pk=self.identity["pk"])
        self.assertEqual(reversed_product.category_id, self.identity["category_pk"])
        self.assertEqual(reversed_product.catalog_scope, "general")
        self.assertEqual(reversed_product.canonical_section, "")
        self.assertEqual(reversed_product.canonical_category_slug, "")
        self.assertEqual(
            set(reversed_product.tags.values_list("pk", flat=True)),
            {self.identity["proposal_pk"]},
        )
