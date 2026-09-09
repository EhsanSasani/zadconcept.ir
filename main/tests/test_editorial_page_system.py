from pathlib import Path

from django.test import TestCase
from django.urls import reverse


class EditorialPageSystemTests(TestCase):
    template_root = Path(__file__).resolve().parents[1] / "templates" / "main"

    redesigned_templates = (
        "pages/catalog/section.html",
        "pages/catalog/landing.html",
        "pages/catalog/subcategory.html",
        "pages/occasions/index.html",
        "pages/occasions/detail.html",
        "pages/products/detail.html",
        "pages/weddings/collection.html",
        "pages/workshops/redesign.html",
        "pages/workshops/detail.html",
        "pages/international/orders_fa.html",
        "pages/international/orders_en.html",
        "pages/local/hub.html",
        "pages/local/landing.html",
        "pages/blog/index.html",
        "pages/blog/detail.html",
        "pages/content/about.html",
        "pages/content/contact.html",
        "pages/content/faq.html",
        "pages/content/policy.html",
        "errors/404.html",
    )

    locked_templates = (
        "pages/home/index.html",
        "pages/weddings/index.html",
    )

    def test_all_active_target_templates_opt_into_editorial_system(self):
        for relative_path in self.redesigned_templates:
            with self.subTest(template=relative_path):
                source = (self.template_root / relative_path).read_text(encoding="utf-8")
                self.assertIn("page-zad-v2", source)
                self.assertIn("pages/shared/zad-editorial.css", source)

    def test_locked_landings_do_not_opt_into_editorial_system(self):
        for relative_path in self.locked_templates:
            with self.subTest(template=relative_path):
                source = (self.template_root / relative_path).read_text(encoding="utf-8")
                self.assertNotIn("page-zad-v2", source)
                self.assertNotIn("pages/shared/zad-editorial.css", source)

        landing_source = (self.template_root / "pages/catalog/landing.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('{% if section != "flowers" %} page-zad-v2{% endif %}', landing_source)
        self.assertIn(
            '{% if section != "flowers" %}<link rel="stylesheet" href="{% static '
            "'main/css/pages/shared/zad-editorial.css' %}?v=1\">{% endif %}",
            landing_source,
        )

    def test_editorial_css_keeps_flower_hero_contract_and_responsive_grids(self):
        css_path = (
            Path(__file__).resolve().parents[1]
            / "static"
            / "main"
            / "css"
            / "pages"
            / "shared"
            / "zad-editorial.css"
        )
        source = css_path.read_text(encoding="utf-8")
        self.assertIn("height: var(--zad-home-hero-desktop", source)
        self.assertIn("height: calc(56.25vw + 76px)", source)
        self.assertIn("margin-top: -24px", source)
        self.assertIn("border-radius: 28px 28px 0 0", source)
        self.assertIn("repeat(2, minmax(0, 1fr))", source)
        self.assertIn("@media (prefers-reduced-motion: reduce)", source)

    def test_representative_public_pages_render_editorial_system(self):
        route_names = (
            "bakery",
            "gifts",
            "flowers_same_day",
            "occasions",
            "events",
            "mashhad_hub",
            "mashhad_flower_order",
            "mashhad_flower_delivery",
            "contact",
            "faq",
            "about",
            "privacy",
            "terms",
            "delivery_policy",
            "refund_policy",
            "payment_methods",
            "service_area",
            "international_orders",
            "international_orders_en",
            "blog",
        )

        for route_name in route_names:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "page-zad-v2")
                self.assertContains(response, "pages/shared/zad-editorial.css")

    def test_locked_landings_render_without_editorial_opt_in(self):
        for route_name in ("index", "flowers", "weddings"):
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "page-zad-v2")
                self.assertNotContains(response, "pages/shared/zad-editorial.css")
