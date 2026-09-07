"""Managed product data and category navigation in the approved home design."""
from html.parser import HTMLParser
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.urls import reverse


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.items = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


class HomeDailyOccasionsTests(SimpleTestCase):
    def render(self, products=(), occasions=()):
        return render_to_string("main/components/home_daily_occasions.html", {
            "home_same_day_products": products,
            "home_occasion_cards": occasions,
        })

    def product(self, **changes):
        data = dict(
            name='رز "هلویی"', product_code="0407", seo_name="رز هلویی زاد",
            category=SimpleNamespace(name="دسته‌گل", slug="bouquet"),
            stock_status="in_stock", stock_status_label="موجود",
            has_price=True, display_price="1,250,000 تومان · 20 USD",
            order_contact_text="هماهنگی سفارش", description="توضیحات <محصول>",
            get_absolute_url="/products/407/",
            cover_image=SimpleNamespace(url="/media/products/rose.webp"),
            cover_srcset="/media/products/rose-520.webp 520w, /media/products/rose-900.webp 900w",
        )
        data.update(changes)
        return SimpleNamespace(**data)

    def test_real_product_media_price_and_modal_payload_survive_redesign(self):
        product = self.product()
        html = self.render([product])
        elements = Elements(html).items
        card = next(attrs for _, attrs in elements if "data-catalog-card" in attrs)
        for key, value in {
            "data-product-name": product.name,
            "data-product-code": product.product_code,
            "data-product-price": product.display_price,
            "data-product-description": product.description,
            "data-product-contact": product.order_contact_text,
            "data-product-stock": product.stock_status_label,
        }.items():
            self.assertEqual(card[key], value)
        link = next(attrs for _, attrs in elements if "data-zad-modal-card" in attrs)
        self.assertEqual(link["href"], product.get_absolute_url)
        image = next(attrs for _, attrs in elements if "data-product-image" in attrs)
        self.assertEqual(image["src"], product.cover_image.url)
        self.assertEqual(image["srcset"], product.cover_srcset)
        self.assertEqual(image["alt"], product.seo_name)
        self.assertIn(product.display_price, html)

    def test_badge_never_claims_unavailable_or_preorder_stock_is_ready(self):
        for status, label in (("in_stock", "آماده ارسال"), ("out_of_stock", "ناموجود"), ("preorder", "پیش‌سفارش")):
            with self.subTest(status=status):
                html = self.render([self.product(stock_status=status)])
                self.assertIn(f">{label}</span>", html)
                if status != "in_stock":
                    self.assertNotIn(">آماده ارسال</span>", html)

    def test_unnamed_inquiry_product_has_category_and_code_without_fake_price(self):
        html = self.render([self.product(name="", has_price=False, display_price="استعلام قیمت", cover_image=None)])
        self.assertIn("<strong>دسته‌گل</strong>", html)
        self.assertIn("<bdi>0407</bdi>", html)
        self.assertIn('data-product-price="استعلام قیمت"', html)
        self.assertNotIn('class="zad-shop-card__price"', html)
        image = next(attrs for _, attrs in Elements(html).items if "data-product-image" in attrs)
        self.assertEqual(image["src"], "/static/main/img/sub-bouquet.webp")

    def test_all_managed_occasion_links_and_remote_media_are_preserved(self):
        images = ["/media/occasions/birthday.webp", "https://cdn.example.com/anniversary.webp", "main/img/occasions/special.webp"]
        occasions = [dict(label=f"مناسبت {i}", label_en=f"Occasion {i}", url=f"/occasions/{i}/", image=image) for i, image in enumerate(images)]
        elements = Elements(self.render(occasions=occasions)).items
        links = [attrs["href"] for tag, attrs in elements if tag == "a"]
        sources = [attrs["src"] for tag, attrs in elements if tag == "img"]
        for item in occasions:
            self.assertIn(item["url"], links)
        for image in images[:2]:
            self.assertIn(image, sources)
        self.assertIn("/static/" + images[2], sources)
        self.assertIn(reverse("occasions"), links)

    def test_empty_sections_have_working_catalog_links_without_false_stock(self):
        html = self.render()
        self.assertNotIn('data-zad-modal-card', html)
        self.assertNotIn('class="zad-shop-card__badge"', html)
        self.assertIn(f'href="{reverse("flowers")}"', html)
        self.assertIn(f'href="{reverse("occasions")}"', html)
