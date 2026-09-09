from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from main.category_presentation import _category_card
from main.models import Category


class FlowerStudioLandingTests(TestCase):
    slugs = ("hand-bouquet", "box", "bouquet", "jarl", "stand", "plants")

    @classmethod
    def setUpTestData(cls):
        cls.categories = [
            Category.objects.create(
                name=f"Flower category {index}",
                slug=slug,
                section=Category.Section.FLOWERS,
                sort_order=index,
            )
            for index, slug in enumerate(cls.slugs)
        ]

    def test_directory_renders_responsive_fallbacks_and_single_cta(self):
        response = self.client.get(reverse("flowers"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "main/css/pages/catalog/flower-studio.css",
        )
        for slug in self.slugs:
            with self.subTest(slug=slug):
                self.assertContains(
                    response,
                    f"main/img/flowers/categories/{slug}-640.webp",
                )
                self.assertContains(
                    response,
                    f"main/img/flowers/categories/{slug}-960.webp",
                )

        self.assertContains(response, 'class="flowers-btn"', count=1)
        self.assertNotContains(response, "هماهنگی در تلگرام")

    def test_admin_category_cover_remains_authoritative(self):
        category = self.categories[0]
        category.cover_image = "categories/admin-hand-bouquet.webp"
        category.save(update_fields=["cover_image"])

        card = _category_card(category)

        self.assertEqual(card["image"], "/media/categories/admin-hand-bouquet.webp")
        self.assertEqual(card["image_640"], "")
        self.assertEqual(card["image_960"], "")

    def test_css_carries_home_hero_and_responsive_grid_contract(self):
        css = (
            Path(settings.BASE_DIR)
            / "main/static/main/css/pages/catalog/flower-studio.css"
        ).read_text(encoding="utf-8")

        self.assertIn("height: var(--zad-home-hero-desktop", css)
        self.assertIn("height: calc(56.25vw + 76px) !important", css)
        self.assertIn("position: sticky !important", css)
        self.assertIn("margin-top: -18px", css)
        self.assertIn("border-radius: 24px 24px 0 0", css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", css)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", css)
