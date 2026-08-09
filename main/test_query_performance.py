from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import Category, Product, ProductImage, Tag
from .selectors.catalog import (
    catalog_categories_with_child_state,
    catalog_products_for_section,
    ordered_catalog_products,
    product_detail_products,
)
from .selectors.weddings import wedding_products_by_type


class CatalogQueryBudgetTests(TestCase):
    """Keep public catalog query counts bounded as result sets grow."""

    @classmethod
    def setUpTestData(cls):
        cls.flowers = Category.objects.create(
            name="Query Flowers",
            slug="query-flowers",
            section=Category.Section.FLOWERS,
        )
        cls.child = Category.objects.create(
            name="Query Flower Child",
            slug="query-flower-child",
            section=Category.Section.FLOWERS,
            parent=cls.flowers,
        )
        cls.birthday = Tag.objects.create(
            name="Query Birthday",
            slug="query-birthday",
            is_active=True,
            is_occasion=True,
        )
        cls.same_day, _ = Tag.objects.update_or_create(
            slug="same-day",
            defaults={
                "name": "ارسال روز تست Query",
                "is_active": True,
            },
        )

        cls.products = []
        for index in range(16):
            product = Product.objects.create(
                name=f"Query Product {index}",
                category=cls.child,
                is_active=True,
                publish_status=Product.PublishStatus.PUBLISHED,
                featured=index < 2,
                sort_order=index,
            )
            product.tags.add(cls.birthday, cls.same_day)
            cls.products.append(product)

        cls.product = cls.products[0]
        ProductImage.objects.create(
            product=cls.product,
            image="products/gallery/query-product.webp",
            alt_text="Query product gallery",
        )

    def assert_page_query_budget(self, path, maximum):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            response.content

        query_count = len(captured)
        self.assertLessEqual(
            query_count,
            maximum,
            f"{path} used {query_count} queries; budget is {maximum}.",
        )
        return query_count

    def test_card_selector_has_no_per_product_or_parent_queries(self):
        with self.assertNumQueries(1):
            products = list(
                ordered_catalog_products(
                    catalog_products_for_section(Category.Section.FLOWERS)
                )
            )
            rendered_state = [
                (
                    product.category.name,
                    product.category.parent.name,
                    product.card_type_label,
                )
                for product in products
            ]

        self.assertEqual(len(rendered_state), 16)

    def test_category_child_state_is_annotated_without_n_plus_one(self):
        with self.assertNumQueries(1):
            categories = list(
                catalog_categories_with_child_state(Category.Section.FLOWERS)
            )
            child_state = {
                category.slug: category.has_active_children
                for category in categories
            }

        self.assertTrue(child_state[self.flowers.slug])
        self.assertFalse(child_state[self.child.slug])

    def test_detail_selector_prefetches_tags_and_gallery(self):
        with self.assertNumQueries(3):
            product = product_detail_products().get(pk=self.product.pk)
            tag_slugs = [tag.slug for tag in product.tags.all()]
            gallery_alts = [image.alt_text for image in product.gallery_images.all()]

        self.assertEqual(set(tag_slugs), {self.birthday.slug, self.same_day.slug})
        self.assertEqual(gallery_alts, ["Query product gallery"])

    def test_representative_public_page_budgets(self):
        budgets = {
            reverse("index"): 18,
            reverse("flowers"): 14,
            reverse("flower_subcategory", args=[self.child.slug]): 16,
            self.product.get_absolute_url(): 16,
        }

        for path, maximum in budgets.items():
            with self.subTest(path=path):
                self.assert_page_query_budget(path, maximum)

    def test_collection_pagination_replaces_fixed_result_slices(self):
        path = reverse("flower_subcategory", args=[self.child.slug])

        first_page = self.client.get(path)
        second_page = self.client.get(path, {"page": 2})

        self.assertEqual(len(first_page.context["items"]), 12)
        self.assertEqual(len(second_page.context["items"]), 4)
        self.assertEqual(second_page.context["catalog_page_obj"].number, 2)
        self.assertEqual(second_page.context["robots_content"], "index,follow")
        self.assertTrue(second_page.context["canonical_url"].endswith("?page=2"))
        self.assertContains(second_page, 'aria-current="page"')

    def test_legacy_flowers_page_query_redirects_to_the_directory(self):
        response = self.client.get(reverse("flowers"), {"page": 2})

        self.assertRedirects(
            response,
            reverse("flowers"),
            status_code=301,
            fetch_redirect_response=False,
        )


class WeddingQueryBudgetTests(TestCase):
    """Wedding landing and collections stay constant-query as products grow."""

    @classmethod
    def setUpTestData(cls):
        root, _ = Category.objects.update_or_create(
            slug="wedding",
            section=Category.Section.FLOWERS,
            defaults={
                "name": "Query Wedding",
                "parent": None,
                "is_active": True,
            },
        )
        category_specs = (
            (
                Product.WeddingType.PROPOSAL_BOUQUET,
                Category.Section.FLOWERS,
                "proposal-bale-boroon-bouquet",
                "Query Proposal Bouquets",
                root,
            ),
            (
                Product.WeddingType.PROPOSAL_SWEETS,
                Category.Section.BAKERY,
                "proposal-bale-boroon-sweets",
                "Query Proposal Sweets",
                None,
            ),
            (
                Product.WeddingType.BRIDAL_BOUQUET,
                Category.Section.FLOWERS,
                "bridal-bouquet",
                "Query Bridal Bouquets",
                root,
            ),
            (
                Product.WeddingType.WEDDING_CAR,
                Category.Section.FLOWERS,
                "wedding-car",
                "Query Wedding Cars",
                root,
            ),
        )
        cls.categories = {}
        for wedding_type, section, slug, name, parent in category_specs:
            category, _ = Category.objects.update_or_create(
                section=section,
                slug=slug,
                defaults={"name": name, "parent": parent, "is_active": True},
            )
            cls.categories[wedding_type] = category
            for index in range(12):
                Product.objects.create(
                    name=f"Wedding Query {wedding_type} {index}",
                    category=category,
                    catalog_scope=Product.CatalogScope.WEDDING,
                    wedding_type=wedding_type,
                    wedding_sort_order=index,
                    publish_status=Product.PublishStatus.PUBLISHED,
                )

    def assert_page_query_budget(self, path, maximum):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            response.content
        self.assertLessEqual(
            len(captured),
            maximum,
            f"{path} used {len(captured)} queries; budget is {maximum}.",
        )

    def test_grouping_all_wedding_cards_is_one_query(self):
        with self.assertNumQueries(1):
            grouped = wedding_products_by_type()
            rendered_state = [
                (product.category.name, product.card_type_label)
                for products in grouped.values()
                for product in products
            ]

        self.assertEqual(len(rendered_state), 48)

    def test_wedding_public_page_budgets(self):
        self.assert_page_query_budget(reverse("weddings"), 10)
        for slug in (
            "proposal-bouquets",
            "proposal-sweets",
            "bridal-bouquets",
            "wedding-cars",
        ):
            with self.subTest(slug=slug):
                self.assert_page_query_budget(
                    reverse("wedding_collection", args=[slug]),
                    10,
                )
