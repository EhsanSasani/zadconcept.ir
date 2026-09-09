from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ..context_processors import full_address_text
from ..models import Category, PageContentBlock, Product, Tag
from ..sitemaps import OccasionSitemap
from ..views import _active_occasion_tags


class AdminResponsiveRegressionTests(SimpleTestCase):
    def test_mobile_sidebar_uses_the_dedicated_drawer_state(self):
        css_path = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "main"
            / "css"
            / "admin_modern.css"
        )
        css = css_path.read_text(encoding="utf-8")

        self.assertIn('grid-template-areas:', css)
        self.assertIn("@media (max-width: 991.98px)", css)
        self.assertRegex(
            css,
            r"body \.zad-sidebar \{[^}]*transform: translateX\(100%\) !important;"
            r"[^}]*visibility: hidden !important;[^}]*pointer-events: none !important;",
        )
        self.assertRegex(
            css,
            r"body\.zad-menu-open \.zad-sidebar \{[^}]*visibility: visible !important;"
            r"[^}]*pointer-events: auto !important;[^}]*transform: translateX\(0\)",
        )
        self.assertIn("body .zad-menu-backdrop:not([hidden])", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)


class PublicCopyRegressionTests(TestCase):
    def test_address_starts_with_mashhad_without_duplication(self):
        street = "بلوار وکیل‌آباد - نبش فارغ‌التحصیلان ۶ - کانسپت زاد"

        self.assertEqual(
            full_address_text(street, "مشهد"),
            f"مشهد، {street}",
        )
        self.assertEqual(
            full_address_text(f"مشهد، {street}", "مشهد"),
            f"مشهد، {street}",
        )

    def test_retired_home_copy_does_not_replace_the_approved_discover(self):
        PageContentBlock.objects.create(
            page=PageContentBlock.Page.HOME,
            section_key="flowers",
            title="عنوان آرشیوی جایگاه گل‌ها",
        )

        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "استودیو گل زاد")
        self.assertContains(response, 'id="home-explore-title"')
        self.assertContains(response, '<strong dir="rtl">استودیو گل</strong>', html=True)
        self.assertNotContains(response, "عنوان آرشیوی جایگاه گل‌ها")


class WeddingCatalogRegressionTests(TestCase):
    def setUp(self):
        self.wedding, _ = Category.objects.update_or_create(
            section=Category.Section.FLOWERS,
            slug="wedding",
            defaults={
                "name": "عروسی",
                "parent": None,
                "is_active": True,
                "sort_order": 50,
            },
        )
        self.wedding_car, _ = Category.objects.update_or_create(
            section=Category.Section.FLOWERS,
            slug="wedding-car",
            defaults={
                "name": "ماشین عروس",
                "parent": self.wedding,
                "is_active": True,
                "sort_order": 10,
            },
        )
        self.bridal_bouquet, _ = Category.objects.update_or_create(
            section=Category.Section.FLOWERS,
            slug="bridal-bouquet",
            defaults={
                "name": "دسته‌گل عروس",
                "parent": self.wedding,
                "is_active": True,
                "sort_order": 20,
            },
        )
        self.car_product = Product.objects.create(
            name="گل‌آرایی خودرو تست",
            category=self.wedding_car,
            catalog_scope=Product.CatalogScope.WEDDING,
            wedding_type=Product.WeddingType.WEDDING_CAR,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        self.bouquet_product = Product.objects.create(
            name="دسته‌گل عروس تست",
            category=self.bridal_bouquet,
            catalog_scope=Product.CatalogScope.WEDDING,
            wedding_type=Product.WeddingType.BRIDAL_BOUQUET,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

    def test_wedding_products_only_render_in_their_dedicated_collections(self):
        flowers_response = self.client.get(reverse("flowers"))
        wedding_response = self.client.get(reverse("weddings"))
        car_response = self.client.get(
            reverse(
            "wedding_collection",
            kwargs={"collection_slug": "wedding-cars"},
        )
        )
        bouquet_response = self.client.get(
            reverse(
            "wedding_collection",
            kwargs={"collection_slug": "bridal-bouquets"},
        )
        )

        self.assertEqual(flowers_response.status_code, 200)
        self.assertEqual(wedding_response.status_code, 200)
        self.assertEqual(car_response.status_code, 200)
        self.assertEqual(bouquet_response.status_code, 200)

        self.assertNotContains(flowers_response, self.car_product.name)
        self.assertNotContains(flowers_response, self.bouquet_product.name)

        self.assertNotContains(wedding_response, self.car_product.name)
        self.assertNotContains(wedding_response, self.bouquet_product.name)

        self.assertContains(car_response, self.car_product.name)
        self.assertNotContains(car_response, self.bouquet_product.name)

        self.assertContains(bouquet_response, self.bouquet_product.name)
        self.assertNotContains(bouquet_response, self.car_product.name)

    def test_parent_category_rejects_new_untyped_products(self):
        direct_product = Product(
            name="محصول مستقیم عروسی",
            category=self.wedding,
        )

        with self.assertRaises(ValidationError):
            direct_product.full_clean()

    def test_wedding_is_not_an_occasion_and_legacy_urls_are_canonicalized(self):
        wedding_tag, _ = Tag.objects.update_or_create(
            slug="wedding",
            defaults={
                "name": "عروسی",
                "is_active": True,
                "is_occasion": True,
            },
        )

        old_global_url = self.client.get(
            reverse("occasion_detail", args=["wedding"])
        )
        old_flower_url = self.client.get(
            reverse("flower_occasion", args=["wedding"])
        )

        self.assertNotIn(wedding_tag, _active_occasion_tags())
        self.assertNotIn(wedding_tag, list(OccasionSitemap().items()))
        self.assertRedirects(
            old_global_url,
            reverse("weddings"),
            status_code=301,
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            old_flower_url,
            reverse("weddings"),
            status_code=301,
            fetch_redirect_response=False,
        )


class ProductAdminSearchRegressionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="hotfix-admin",
            email="hotfix-admin@example.invalid",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.category = Category.objects.create(
            name="باکس گل",
            slug="box",
            section=Category.Section.FLOWERS,
        )
        self.product = Product.objects.create(
            name="باکس رز جست‌وجو",
            category=self.category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        self.url = reverse("admin:main_flower_changelist")

    def test_search_finds_product_by_name_and_persian_code(self):
        by_name = self.client.get(self.url, {"q": "رز جست‌وجو"})
        persian_code = self.product.product_code.translate(
            str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        )
        by_code = self.client.get(self.url, {"q": persian_code})

        self.assertEqual(by_name.status_code, 200)
        self.assertEqual(by_code.status_code, 200)
        self.assertContains(by_name, self.product.name)
        self.assertContains(by_code, self.product.name)
        self.assertContains(
            by_code,
            "کد با رقم فارسی یا انگلیسی قابل جست‌وجو است",
        )
        self.assertContains(by_code, "main/css/admin_custom.css")

    def test_parent_and_child_categories_remain_selectable_in_admin(self):
        child = Category.objects.create(
            name="باکس تولد",
            slug="birthday-box",
            section=Category.Section.FLOWERS,
            parent=self.category,
        )

        response = self.client.get(reverse("admin:main_flower_add"))
        category_field = response.context["adminform"].form.fields["category"]

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.category, category_field.queryset)
        self.assertIn(child, category_field.queryset)
