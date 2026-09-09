"""Rendered structure regressions: later/conditional sections cannot escape the cover."""
from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse


class Element:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    def has_class(self, name):
        return name in self.attrs.get("class", "").split()


class Document(HTMLParser):
    void = set("area base br col embed hr img input link meta param source track wbr".split())

    def __init__(self, html):
        super().__init__()
        self.root = Element("document", [])
        self.current = self.root
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs, self.current)
        self.current.children.append(node)
        self.elements.append(node)
        if tag not in self.void:
            self.current = node

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent


class ScrollSurfaceTests(TestCase):
    def test_all_nested_hero_pages_have_one_unbroken_cover_until_shell_end(self):
        cases = (
            ("index", "home-hero"), ("flowers", "flowers-hero"),
            ("bakery", "flowers-hero"), ("gifts", "flowers-hero"),
            ("weddings", "weddings-hero"), ("about", "about-hero"),
            ("events", "wsr-hero"),
            ("international_orders", "io-hero"),
            ("international_orders_en", "io-hero"),
        )
        for route, hero_class in cases:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                doc = Document(response.content.decode())
                hero = next(n for n in doc.elements if n.has_class(hero_class))
                covers = [n for n in doc.elements if n.has_class("zad-scroll-content")]
                self.assertEqual(len(covers), 1)
                cover = covers[0]
                self.assertIs(cover.parent, hero.parent)
                siblings = hero.parent.children
                self.assertEqual(siblings[siblings.index(hero) + 1:], [cover])
                self.assertTrue(cover.children)
                footer = next(n for n in doc.elements if n.has_class("zad-footer"))
                self.assertEqual(footer.parent.tag, "body")
                styles = [n.attrs.get("href", "") for n in doc.elements if n.tag == "link" and n.attrs.get("rel") == "stylesheet"]
                self.assertIn("scroll-system.css", styles[-1])

    def test_both_wedding_gallery_layouts_remain_inside_the_cover(self):
        from main.models import WeddingGalleryImage, WeddingPageContent

        page = WeddingPageContent.objects.create()
        for count in range(1, 6):
            WeddingGalleryImage.objects.create(
                page=page, image=f"weddings/gallery/example-{count}.webp"
            )
            if count not in (1, 5):
                continue
            with self.subTest(images=count):
                doc = Document(self.client.get(reverse("weddings")).content.decode())
                gallery = next(n for n in doc.elements if n.has_class("weddings-gallery"))
                self.assertTrue(gallery.parent.has_class("zad-scroll-content"))
                layout = "weddings-gallery__fallback" if count == 1 else "weddings-gallery__mosaic"
                self.assertTrue(any(n.has_class(layout) for n in doc.elements))
