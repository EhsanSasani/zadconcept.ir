from html.parser import HTMLParser

from django.test import TestCase

from main.models import Category, Product


class Headings(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.count = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "h1":
            self.count += 1


class CollectionHeaderTests(TestCase):
    def test_preview_uses_a_published_collection_product_and_survives_filtering(self):
        category = Category.objects.create(name="باکس گل", slug="header-box", section="flowers")
        Product.objects.create(category=category, name="پیش‌نویس", publish_status="draft", featured=True, cover_image="products/private.webp")
        preview = Product.objects.create(category=category, name="باکس نمونه", publish_status="published", cover_image="products/box.webp")
        for suffix in ("", "?tag=unique"):
            response = self.client.get(category.get_absolute_url() + suffix)
            self.assertEqual(response.context["collection_preview"], preview)
            self.assertContains(response, f'src="{preview.cover_image.url}"')
            self.assertNotContains(response, "products/private.webp")

    def test_all_shop_sections_get_one_heading_and_the_correct_return_link(self):
        for section in ("flowers", "bakery", "gifts"):
            with self.subTest(section=section):
                category = Category.objects.create(name=f"مجموعه {section}", slug=f"header-{section}", section=section)
                response = self.client.get(category.get_absolute_url())
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="collection-header"')
                self.assertContains(response, f'href="/{section}/" class="collection-header__back"')
                self.assertNotContains(response, 'category-split-hero__card')
                self.assertEqual(Headings(response.content.decode()).count, 1)

    def test_parent_collection_directory_does_not_repeat_the_heading(self):
        parent = Category.objects.create(name="مجموعه مادر", slug="header-parent", section="gifts")
        Category.objects.create(name="زیرمجموعه", slug="header-child", section="gifts", parent=parent)
        response = self.client.get(parent.get_absolute_url())
        self.assertContains(response, "انتخاب مجموعه")
        self.assertEqual(Headings(response.content.decode()).count, 1)
