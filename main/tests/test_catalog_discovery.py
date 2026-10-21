from urllib.parse import parse_qs, urlsplit

from django.test import TestCase
from django.urls import reverse

from main.models import Category, Product, Tag
from main.tests.test_seo import graph_for, parse_html


class CatalogDiscoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category, _ = Category.objects.get_or_create(
            section=Category.Section.FLOWERS, slug="hand-bouquet",
            defaults={"name": "دسته گل"},
        )
        cls.products = [
            Product.objects.create(
                name=f"دسته گل نمونه {number}", category=cls.category,
                sort_order=number, publish_status=Product.PublishStatus.PUBLISHED,
            )
            for number in range(49)
        ]
        cls.url = cls.category.get_absolute_url()

    def test_category_pagination_discovers_every_product_without_duplicates(self):
        first = self.client.get(self.url)
        second = self.client.get(self.url, {"page": 2})
        self.assertEqual(len(first.context["items"]), 48)
        self.assertEqual([p.pk for p in second.context["items"]], [self.products[-1].pk])
        self.assertContains(first, f'href="{self.url}?page=2" rel="next"')
        self.assertContains(second, f'href="{self.url}" rel="prev"')
        self.assertEqual(parse_html(second).canonical, f"https://www.zadconcept.ir{self.url}?page=2")
        self.assertEqual(parse_html(second).robots, "index,follow")
        self.assertEqual(self.client.get(self.url, {"page": 3}).status_code, 404)

    def test_schema_matches_each_visible_page_and_uses_collection_name(self):
        for number in (1, 2):
            response = self.client.get(self.url, {"page": number})
            graph = graph_for(response)
            listing = next(n for n in graph if n["@type"] == "ItemList")
            collection = next(n for n in graph if n["@type"] == "CollectionPage")
            self.assertEqual(collection["mainEntity"]["@id"], listing["@id"])
            self.assertEqual(listing["name"], self.category.name)
            self.assertEqual(listing["numberOfItems"], len(response.context["items"]))
            self.assertEqual(
                [item["url"] for item in listing["itemListElement"]],
                [f"https://www.zadconcept.ir{p.get_absolute_url()}" for p in response.context["items"]],
            )

    def test_filter_pagination_keeps_filter_and_is_not_indexable(self):
        tag, _ = Tag.objects.update_or_create(
            slug="unique", defaults={"name": "یونیک", "is_active": True},
        )
        for product in self.products:
            product.tags.add(tag)
        response = self.client.get(self.url, {"tag": "unique"})
        next_url = response.context["catalog_pagination"]["next"]
        self.assertEqual(parse_qs(urlsplit(next_url).query), {"tag": ["unique"], "page": ["2"]})
        second = self.client.get(next_url)
        self.assertEqual(parse_html(second).robots, "noindex,follow")
        self.assertEqual(parse_html(second).canonical, f"https://www.zadconcept.ir{self.url}")
        self.assertNotContains(second, 'id="collection-guide-title"')

    def test_all_products_page_is_also_paginated(self):
        url = reverse("flowers_all")
        response = self.client.get(url, {"page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p.pk for p in response.context["items"]], [self.products[-1].pk])
        self.assertEqual(parse_html(response).canonical, f"https://www.zadconcept.ir{url}?page=2")
        self.assertEqual(parse_html(response).robots, "index,follow")

    def test_buying_guide_is_visible_once_and_links_to_real_service_pages(self):
        response = self.client.get(self.url)
        self.assertContains(response, "انتخاب و سفارش دسته‌گل در مشهد")
        self.assertContains(response, reverse("flowers_same_day"))
        self.assertContains(response, reverse("mashhad_flower_order"))
        self.assertContains(response, 'href="tel:')
        self.assertNotContains(self.client.get(self.url, {"page": 2}), 'id="collection-guide-title"')
        self.assertEqual(parse_html(response).h1_count, 1)

    def test_ready_sold_and_draft_products_do_not_leak_into_category_pages(self):
        for values in (
            {"publish_status": Product.PublishStatus.DRAFT},
            {"catalog_scope": Product.CatalogScope.SAME_DAY, "status": Product.Status.SOLD},
        ):
            data = {"publish_status": Product.PublishStatus.PUBLISHED, **values}
            product = Product.objects.create(
                name="نباید نمایش داده شود", category=self.category, **data,
            )
            response = self.client.get(self.url)
            graph = graph_for(response)
            listing = next(n for n in graph if n["@type"] == "ItemList")
            self.assertNotIn(f"https://www.zadconcept.ir{product.get_absolute_url()}", [n["url"] for n in listing["itemListElement"]])
