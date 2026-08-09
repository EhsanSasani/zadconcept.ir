from django.test import TestCase

from .models import (
    Category,
    Product,
    SameDayFlower,
    Tag,
    category_cover_upload_to,
)
from .selectors.catalog import (
    active_occasion_tags,
    published_products,
    same_day_flower_products,
)


class ArchitectureContractTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Architecture Flowers",
            slug="architecture-flowers",
            section=Category.Section.FLOWERS,
        )

    def test_view_facade_exports_domain_modules(self):
        from . import views

        self.assertEqual(views.index.__module__, "main.views.home")
        self.assertEqual(views.flowers.__module__, "main.views.catalog")
        self.assertEqual(views.product_detail.__module__, "main.views.products")
        self.assertEqual(views.occasions.__module__, "main.views.occasions")
        self.assertEqual(views.events.__module__, "main.views.workshops")
        self.assertEqual(views.submit_lead_request.__module__, "main.views.leads")
        self.assertEqual(views.custom_404.__module__, "main.views.system")

    def test_historical_migration_callback_path_is_stable(self):
        self.assertEqual(category_cover_upload_to.__module__, "main.models")

    def test_public_selector_enforces_publication_contract(self):
        visible = Product.objects.create(
            name="Visible",
            category=self.category,
            is_active=True,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        Product.objects.create(
            name="Draft",
            category=self.category,
            is_active=True,
            publish_status=Product.PublishStatus.DRAFT,
        )
        Product.objects.create(
            name="Inactive",
            category=self.category,
            is_active=False,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

        self.assertEqual(list(published_products()), [visible])

    def test_same_day_and_occasion_policies_are_centralized(self):
        same_day, _ = Tag.objects.update_or_create(
            slug="same-day",
            defaults={"name": "ارسال روز", "is_active": True},
        )
        birthday, _ = Tag.objects.update_or_create(
            slug="birthday",
            defaults={
                "name": "تولد",
                "is_active": True,
                "is_occasion": True,
            },
        )
        wedding, _ = Tag.objects.update_or_create(
            slug="wedding",
            defaults={
                "name": "عروسی",
                "is_active": True,
                "is_occasion": True,
            },
        )
        product = Product.objects.create(
            name="Same day",
            category=self.category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        product.tags.add(same_day)

        self.assertEqual(list(same_day_flower_products()), [product])
        self.assertEqual(list(SameDayFlower.objects.all()), [product])
        self.assertIn(birthday, active_occasion_tags())
        self.assertNotIn(wedding, active_occasion_tags())

    def test_product_queryset_contracts_are_composable(self):
        published = Product.objects.create(
            name="Published flower",
            category=self.category,
            is_active=True,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        Product.objects.create(
            name="Draft flower",
            category=self.category,
            is_active=True,
            publish_status=Product.PublishStatus.DRAFT,
        )

        queryset = Product.objects.published().for_section(Category.Section.FLOWERS)

        self.assertEqual(list(queryset), [published])
