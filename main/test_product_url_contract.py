from django.test import TestCase
from django.urls import reverse

from .models import Category, Product


class ProductUrlContractTests(TestCase):
    def setUp(self):
        self.flower_category = Category.objects.create(
            name="URL Contract Hand Bouquet",
            slug="url-contract-hand-bouquet",
            section=Category.Section.FLOWERS,
        )
        self.other_flower_category = Category.objects.create(
            name="URL Contract Box",
            slug="url-contract-box",
            section=Category.Section.FLOWERS,
        )
        self.bakery_category = Category.objects.create(
            name="URL Contract Bakery",
            slug="url-contract-bakery",
            section=Category.Section.BAKERY,
        )
        self.gift_category = Category.objects.create(
            name="URL Contract Gift",
            slug="url-contract-gift",
            section=Category.Section.GIFTS,
        )

        self.flower = Product.objects.create(
            name="URL Contract Flower",
            category=self.flower_category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        self.bakery = Product.objects.create(
            name="URL Contract Cake",
            category=self.bakery_category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        self.gift = Product.objects.create(
            name="URL Contract Present",
            category=self.gift_category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

    def _route_name(self, product):
        return {
            Category.Section.FLOWERS: "flower_product_detail",
            Category.Section.BAKERY: "bakery_product_detail",
            Category.Section.GIFTS: "gift_product_detail",
        }[product.canonical_section or product.category.section]

    def _code_alias_url(self, product, category_slug=None):
        return reverse(
            self._route_name(product),
            args=[
                category_slug
                or product.canonical_category_slug
                or product.category.slug,
                product.product_code,
            ],
        )

    def test_canonical_slug_urls_remain_direct_200_for_all_catalog_sections(self):
        for product in (self.flower, self.bakery, self.gift):
            with self.subTest(product=product.product_code):
                response = self.client.get(product.get_absolute_url())
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("Location", response.headers)

    def test_product_code_aliases_redirect_permanently_to_existing_canonical_urls(self):
        for product in (self.flower, self.bakery, self.gift):
            with self.subTest(product=product.product_code):
                response = self.client.get(self._code_alias_url(product))
                self.assertRedirects(
                    response,
                    product.get_absolute_url(),
                    status_code=301,
                    fetch_redirect_response=False,
                )

    def test_wrong_category_redirects_to_the_same_canonical_product_url(self):
        wrong_url = reverse(
            "flower_product_detail",
            args=[self.other_flower_category.slug, self.flower.slug],
        )
        response = self.client.get(wrong_url)
        self.assertRedirects(
            response,
            self.flower.get_absolute_url(),
            status_code=301,
            fetch_redirect_response=False,
        )

        wrong_code_url = reverse(
            "flower_product_detail",
            args=[self.other_flower_category.slug, self.flower.product_code],
        )
        response = self.client.get(wrong_code_url)
        self.assertRedirects(
            response,
            self.flower.get_absolute_url(),
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_draft_and_inactive_products_are_not_exposed_through_code_aliases(self):
        draft = Product.objects.create(
            name="URL Contract Draft",
            category=self.flower_category,
            publish_status=Product.PublishStatus.DRAFT,
        )
        inactive = Product.objects.create(
            name="URL Contract Inactive",
            category=self.flower_category,
            publish_status=Product.PublishStatus.PUBLISHED,
            is_active=False,
        )

        for product in (draft, inactive):
            with self.subTest(product=product.product_code):
                self.assertEqual(
                    self.client.get(self._code_alias_url(product)).status_code,
                    404,
                )

    def test_unknown_product_reference_is_404(self):
        unknown = reverse(
            "flower_product_detail",
            args=[self.flower_category.slug, "99999999"],
        )
        self.assertEqual(self.client.get(unknown).status_code, 404)

    def test_alias_never_becomes_a_duplicate_indexable_product_page(self):
        alias_response = self.client.get(self._code_alias_url(self.flower))
        self.assertEqual(alias_response.status_code, 301)
        self.assertEqual(alias_response.headers["Location"], self.flower.get_absolute_url())

        canonical_response = self.client.get(self.flower.get_absolute_url())
        self.assertEqual(canonical_response.status_code, 200)
        self.assertContains(
            canonical_response,
            f'<link rel="canonical" href="https://www.zadconcept.ir{self.flower.get_absolute_url()}">',
            html=True,
        )
