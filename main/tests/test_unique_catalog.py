from django.test import TestCase
from django.urls import reverse

from ..models import Category, Product, Tag, UNIQUE_TAG_SLUG


class UniqueCategoryFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.box = Category.objects.create(
            name="باکس گل",
            slug="box",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        cls.jarl = Category.objects.create(
            name="جار گل",
            slug="jarl",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        cls.unique_tag = Tag.objects.create(
            name="یونیک",
            slug=UNIQUE_TAG_SLUG,
            is_occasion=True,
            is_active=True,
        )
        cls.regular_box = Product.objects.create(
            name="باکس معمولی",
            category=cls.box,
            publish_status=Product.PublishStatus.PUBLISHED,
            sort_order=10,
        )
        cls.unique_box = Product.objects.create(
            name="باکس یونیک",
            category=cls.box,
            publish_status=Product.PublishStatus.PUBLISHED,
            sort_order=20,
        )
        cls.unique_box.tags.add(cls.unique_tag)
        cls.unique_jarl = Product.objects.create(
            name="جار یونیک",
            category=cls.jarl,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        cls.unique_jarl.tags.add(cls.unique_tag)
        cls.draft_unique_box = Product.objects.create(
            name="باکس یونیک پیش‌نویس",
            category=cls.box,
            publish_status=Product.PublishStatus.DRAFT,
        )
        cls.draft_unique_box.tags.add(cls.unique_tag)

    def test_category_all_view_keeps_every_published_product_and_shows_switch(self):
        response = self.client.get(self.box.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {product.pk for product in response.context["items"]},
            {self.regular_box.pk, self.unique_box.pk},
        )
        self.assertEqual(
            [item["label"] for item in response.context["unique_filter_links"]],
            ["همه", "یونیک"],
        )
        self.assertTrue(response.context["unique_filter_links"][0]["is_active"])
        self.assertContains(response, "catalog-filter--switch")
        self.assertContains(response, f"?tag={UNIQUE_TAG_SLUG}")

    def test_unique_view_is_the_category_and_tag_intersection(self):
        response = self.client.get(
            self.box.get_absolute_url(),
            {"tag": UNIQUE_TAG_SLUG},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [product.pk for product in response.context["items"]],
            [self.unique_box.pk],
        )
        self.assertEqual(response.context["selected_product_tag"], UNIQUE_TAG_SLUG)
        self.assertTrue(response.context["unique_filter_links"][1]["is_active"])
        self.assertEqual(response.context["robots_content"], "noindex,follow")
        self.assertEqual(
            response.context["canonical_url"],
            f"https://www.zadconcept.ir{self.box.get_absolute_url()}",
        )

    def test_filter_stays_hidden_until_the_category_has_a_unique_product(self):
        category = Category.objects.create(
            name="دسته گل",
            slug="hand-bouquet",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        Product.objects.create(
            name="دسته گل معمولی",
            category=category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

        response = self.client.get(category.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["unique_filter_links"], [])
        self.assertNotContains(response, "catalog-filter--switch")

    def test_direct_empty_unique_url_keeps_an_escape_and_clear_empty_state(self):
        category = Category.objects.create(
            name="استند گل",
            slug="stand",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        Product.objects.create(
            name="استند معمولی",
            category=category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

        response = self.client.get(
            category.get_absolute_url(),
            {"tag": UNIQUE_TAG_SLUG},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["items"], [])
        self.assertEqual(len(response.context["unique_filter_links"]), 2)
        self.assertContains(response, "فعلاً محصول یونیکی در این دسته وجود ندارد.")

    def test_unknown_tag_filter_returns_404(self):
        response = self.client.get(self.box.get_absolute_url(), {"tag": "unknown"})

        self.assertEqual(response.status_code, 404)
