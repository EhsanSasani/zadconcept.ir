from django.test import TestCase
from django.urls import reverse

from ..models import Category, Product, Tag, UNIQUE_TAG_SLUG


class SameDayCatalogIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="باکس ارسال روز",
            slug="same-day-box",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        cls.birthday = Tag.objects.create(
            name="تولد ارسال روز",
            slug="same-day-birthday",
            is_occasion=True,
            is_active=True,
        )
        cls.unique = Tag.objects.create(
            name="یونیک ارسال روز",
            slug=UNIQUE_TAG_SLUG,
            is_active=True,
        )
        cls.general = Product.objects.create(
            name="باکس کاتالوگ عمومی",
            category=cls.category,
            publish_status=Product.PublishStatus.PUBLISHED,
            featured=True,
        )
        cls.general.tags.add(cls.birthday)
        cls.same_day = Product.objects.create(
            name="باکس اختصاصی ارسال روز",
            category=cls.category,
            catalog_scope=Product.CatalogScope.SAME_DAY,
            publish_status=Product.PublishStatus.PUBLISHED,
            featured=True,
        )
        cls.same_day.tags.add(cls.birthday, cls.unique)
        cls.same_day_related = Product.objects.create(
            name="باکس مرتبط ارسال روز",
            category=cls.category,
            catalog_scope=Product.CatalogScope.SAME_DAY,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

    def test_same_day_products_only_render_on_same_day_public_surfaces(self):
        same_day_page = self.client.get(reverse("flowers_same_day"))
        all_flowers = self.client.get(reverse("flowers_all"))
        category = self.client.get(self.category.get_absolute_url())
        occasion = self.client.get(
            reverse("occasion_detail", args=[self.birthday.slug])
        )

        self.assertContains(same_day_page, self.same_day.name)
        self.assertContains(same_day_page, self.same_day_related.name)
        self.assertNotContains(same_day_page, self.general.name)

        for response in (all_flowers, category, occasion):
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, self.same_day.name)
            self.assertNotContains(response, self.same_day_related.name)

        self.assertContains(all_flowers, self.general.name)
        self.assertContains(category, self.general.name)
        self.assertContains(occasion, self.general.name)

    def test_home_keeps_same_day_only_inside_its_dedicated_selection(self):
        response = self.client.get(reverse("index"))

        same_day_ids = set(
            response.context["home_same_day_products"].values_list("pk", flat=True)
        )
        featured_ids = {product.pk for product in response.context["featured_today"]}

        self.assertEqual(
            same_day_ids,
            {self.same_day.pk, self.same_day_related.pk},
        )
        self.assertNotIn(self.same_day.pk, featured_ids)
        self.assertNotIn(self.same_day_related.pk, featured_ids)
        self.assertIn(self.general.pk, featured_ids)

    def test_unique_category_filter_cannot_leak_same_day_products(self):
        response = self.client.get(
            self.category.get_absolute_url(),
            {"tag": UNIQUE_TAG_SLUG},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["items"], [])
        self.assertNotContains(response, self.same_day.name)

    def test_same_day_detail_and_related_products_stay_in_same_day_scope(self):
        response = self.client.get(self.same_day.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["category_url"], reverse("flowers_same_day"))
        self.assertEqual(
            [product.pk for product in response.context["similar_items"]],
            [self.same_day_related.pk],
        )
        self.assertNotIn(
            self.general.pk,
            [product.pk for product in response.context["similar_items"]],
        )

        general_response = self.client.get(self.general.get_absolute_url())
        self.assertNotIn(
            self.same_day.pk,
            [product.pk for product in general_response.context["similar_items"]],
        )

    def test_same_day_product_detail_remains_indexable(self):
        self.assertTrue(
            Product.objects.publicly_indexable()
            .filter(pk=self.same_day.pk)
            .exists()
        )
