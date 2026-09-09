"""Regression contracts for the approved Moments + Discover composition."""
from html.parser import HTMLParser
from pathlib import Path

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.urls import reverse


class ElementCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class HomeMomentsTests(SimpleTestCase):
    def render(self, stories=()):
        return render_to_string(
            "main/components/home_moments_discover.html", {"home_stories": stories}
        )

    @staticmethod
    def story(index=0):
        return {
            "id": index + 1,
            "version": "test-v1",
            "title": f"لحظه‌های ساختن در زاد {index}",
            "cover_url": "/media/stories/cover.webp",
            "clips": [
                {"id": 1, "media_type": "image", "image_url": "/media/stories/photo.webp", "duration_ms": 6500},
                {"id": 2, "media_type": "video", "video_url": "/media/stories/optimized.mp4", "duration_ms": 8000},
            ],
        }

    def test_no_stories_still_renders_discover_without_empty_controls(self):
        html = self.render()
        self.assertIn('class="zad-discover__grid"', html)
        self.assertNotIn("data-moments-rail", html)
        self.assertNotIn("data-story-viewer", html)
        self.assertIn("ZAD FLOWER STUDIO", html)

    def test_four_cards_keep_visual_order_and_real_routes(self):
        parser = ElementCollector()
        parser.feed(self.render())
        cards = [attrs for tag, attrs in parser.elements if tag == "a" and attrs.get("class") == "zad-discover-card"]
        self.assertEqual([card["href"] for card in cards], [reverse(name) for name in ("flowers", "weddings", "bakery", "events")])

    def test_responsive_images_exist_and_have_intrinsic_dimensions(self):
        parser = ElementCollector()
        parser.feed(self.render())
        images = [attrs for tag, attrs in parser.elements if tag == "img"]
        self.assertEqual(len(images), 4)
        for attrs in images:
            self.assertEqual((attrs["width"], attrs["height"]), ("960", "960"))
            self.assertEqual(attrs["loading"], "lazy")
            self.assertTrue(attrs["alt"])
            self.assertIn("760px", attrs["sizes"])
            for source in attrs["srcset"].split(", "):
                self.assertIsNotNone(finders.find(source.split()[0].removeprefix("/static/")))

    def test_story_count_and_viewer_payload_are_preserved(self):
        for count in (1, 6, 12):
            with self.subTest(count=count):
                html = self.render([self.story(index) for index in range(count)])
                parser = ElementCollector()
                parser.feed(html)
                self.assertEqual(sum("data-story-trigger" in attrs for _, attrs in parser.elements), count)
                self.assertEqual(sum("data-story-viewer" in attrs for _, attrs in parser.elements), 1)
                self.assertEqual(sum("data-story-clip" in attrs for _, attrs in parser.elements), count * 2)
                self.assertIn('data-clip-type="image"', html)
                self.assertIn('data-clip-type="video"', html)
                self.assertIn('data-clip-duration="6500"', html)

    def test_rail_arrows_removed_but_viewer_navigation_remains(self):
        parser = ElementCollector()
        parser.feed(self.render([self.story()]))
        attrs_list = [attrs for _, attrs in parser.elements]
        self.assertFalse(any("data-moments-previous" in attrs or "data-moments-next" in attrs for attrs in attrs_list))
        self.assertTrue(any("data-moments-track" in attrs for attrs in attrs_list))
        self.assertTrue(any("data-story-next" in attrs for attrs in attrs_list))
        self.assertTrue(any("data-story-previous" in attrs for attrs in attrs_list))

    def test_standalone_story_component_does_not_get_moments_controls(self):
        html = render_to_string("main/components/story_rail.html", {"home_stories": [self.story()]})
        self.assertNotIn("data-moments-rail", html)
        self.assertIn("data-story-viewer", html)

    def test_heading_and_brand_copy_are_real_html(self):
        html = self.render([self.story()])
        for text in ("لحظه‌های زاد", "ZAD MOMENTS", "دنیای زاد را کشف کنید", "از گل‌ها تا لحظه‌ها، هر آنچه که دنیای شما را زیباتر می‌کند."):
            self.assertIn(text, html)

    def test_stylesheet_does_not_target_locked_components(self):
        path = finders.find("main/css/pages/home/moments-discover.css")
        css = Path(path).read_text()
        for selector in (".site-header", ".zad-utility", ".zad-site-menu", ".site-footer"):
            self.assertNotIn(selector, css)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("repeat(2, minmax(0, 1fr))", css)
        self.assertIn("repeat(4, minmax(0, 1fr))", css)
