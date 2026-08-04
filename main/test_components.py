from django.contrib.messages.storage.base import Message
from django.template.loader import get_template, render_to_string
from django.test import TestCase
from django.urls import reverse

from .models import Category, Product


class TemplateComponentContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Component Flowers",
            slug="component-flowers",
            section=Category.Section.FLOWERS,
        )
        cls.first = Product.objects.create(
            name="First Component Product",
            category=cls.category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        cls.second = Product.objects.create(
            name="Second Component Product",
            category=cls.category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

    def test_shared_component_templates_compile(self):
        component_names = (
            "layout/site_header.html",
            "layout/site_footer.html",
            "layout/flash_messages.html",
            "components/breadcrumbs.html",
            "components/product_card.html",
            "components/product_grid.html",
            "components/product_rail.html",
            "components/hero/standard.html",
        )

        for component_name in component_names:
            with self.subTest(component=component_name):
                self.assertIsNotNone(get_template(component_name))

    def test_product_card_accepts_exactly_one_product(self):
        rendered = render_to_string(
            "components/product_card.html",
            {
                "product": self.first,
                "card_variant": "grid",
                "fallback_image": "main/img/cat-flowers.webp",
            },
        )

        self.assertEqual(rendered.count("data-catalog-card"), 1)
        self.assertIn(self.first.display_name, rendered)
        self.assertNotIn(self.second.display_name, rendered)

    def test_grid_and_rail_own_collection_iteration(self):
        context = {
            "products": [self.first, self.second],
            "fallback_image": "main/img/cat-flowers.webp",
        }

        grid = render_to_string("components/product_grid.html", context)
        rail = render_to_string("components/product_rail.html", context)

        self.assertEqual(grid.count("data-catalog-card"), 2)
        self.assertEqual(rail.count("data-catalog-card"), 2)
        self.assertEqual(rail.count("data-featured-card"), 2)
        self.assertNotIn('class="featured-product-card', rail)

    def test_legacy_card_adapter_preserves_modal_data_contract(self):
        rendered = render_to_string(
            "components/product_card.html",
            {
                "product": self.first,
                "card_variant": "legacy",
                "fallback_image": "main/img/cat-flowers.webp",
            },
        )

        self.assertIn('data-card-variant="legacy"', rendered)
        self.assertIn("data-zad-modal-card", rendered)
        self.assertIn("data-product-image", rendered)
        self.assertIn("data-product-code", rendered)

    def test_standard_hero_preserves_slider_contract(self):
        slides = [
            {
                "title": "First hero",
                "kicker": "FIRST",
                "text": "First text",
                "image": "/media/first.jpg",
                "mobile_image": "/media/first-mobile.jpg",
                "style_class": "hero-light",
                "content_position": "center-left",
                "mobile_content_position": "bottom-center",
            },
            {
                "title": "Second hero",
                "kicker": "SECOND",
                "text": "Second text",
                "image": "/media/second.jpg",
                "mobile_image": "",
                "style_class": "hero-dark",
                "content_position": "center-right",
                "mobile_content_position": "bottom-center",
            },
        ]
        rendered = render_to_string(
            "components/hero/standard.html",
            {
                "page_type": "occasion-detail",
                "page_hero_slides": slides,
                "page_hero_title": "First hero",
                "page_hero_kicker": "FIRST",
                "page_hero_text": "First text",
            },
        )

        self.assertEqual(rendered.count("data-hero-style-class="), 2)
        self.assertEqual(rendered.count("data-page-hero-dot="), 2)
        self.assertIn("data-page-hero-prev", rendered)
        self.assertIn("data-page-hero-next", rendered)
        self.assertIn('fetchpriority="high"', rendered)
        self.assertIn('loading="lazy"', rendered)
        self.assertIn('data-hero-position="center-left"', rendered)

    def test_flash_component_preserves_lead_success_hook(self):
        rendered = render_to_string(
            "layout/flash_messages.html",
            {
                "messages": [
                    Message(level=25, message="درخواست ثبت شد", extra_tags="lead-success")
                ]
            },
        )

        self.assertIn("درخواست ثبت شد", rendered)
        self.assertIn("data-lead-success", rendered)

    def test_breadcrumb_component_marks_current_page(self):
        rendered = render_to_string(
            "components/breadcrumbs.html",
            {
                "breadcrumbs": [
                    {"name": "خانه", "url": "/"},
                    {"name": "محصول", "url": ""},
                ]
            },
        )

        self.assertIn('aria-label="مسیر صفحه"', rendered)
        self.assertIn('aria-current="page"', rendered)
        self.assertIn('href="/"', rendered)

    def test_base_renders_each_layout_landmark_once(self):
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<header class="site-header">', count=1)
        self.assertContains(response, '<main class="site-main">', count=1)
        self.assertContains(response, '<footer class="zad-footer">', count=1)

    def test_hidden_chrome_page_has_no_shared_header_or_footer(self):
        response = self.client.get(reverse("international_orders_en"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<header class="site-header">')
        self.assertNotContains(response, '<footer class="zad-footer">')
