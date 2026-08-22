import base64
import json
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ..models import Category, Product, TelegramBotUser


@override_settings(TELEGRAM_LEAD_RELAY_SECRET="test-relay-secret")
class TelegramProductLookupTests(TestCase):
    url = "/internal/telegram/product-lookup/"

    def post(self, payload, *, authorized=True, telegram_user_id=None):
        headers = {}
        if authorized:
            headers["HTTP_AUTHORIZATION"] = "Bearer test-relay-secret"
        payload = dict(payload)
        if telegram_user_id is not None:
            payload["telegram_user_id"] = telegram_user_id
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def product(self, *, gallery_image=True, cover_image=False):
        images = []
        if gallery_image:
            images.append(
                SimpleNamespace(
                    image=SimpleNamespace(url="/media/products/zad-101.webp")
                )
            )
        return SimpleNamespace(
            product_code="ZAD-101",
            display_name="Test bouquet",
            display_price="2,500,000 تومان",
            cover_image=(
                SimpleNamespace(url="/media/products/zad-101-cover.webp")
                if cover_image
                else None
            ),
            gallery_images=SimpleNamespace(all=lambda: images),
        )

    def telegram_user(self, **overrides):
        values = {
            "name": "Sales user",
            "telegram_user_id": 123456789,
            "can_lookup_products": True,
        }
        values.update(overrides)
        return TelegramBotUser.objects.create(**values)

    def product_query(self, result):
        filtered = Mock()
        filtered.first.return_value = result
        prefetched = Mock()
        prefetched.filter.return_value = filtered
        return prefetched

    def test_rejects_unauthorized_request(self):
        response = self.post({"code": "ZAD-101"}, authorized=False)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Unauthorized")

    def test_rejects_invalid_product_code(self):
        user = self.telegram_user()

        response = self.post(
            {"code": ""},
            telegram_user_id=user.telegram_user_id,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid product code")

    def test_rejects_missing_telegram_user_id(self):
        response = self.post({"code": "ZAD-101"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid Telegram user ID")

    def test_rejects_invalid_telegram_user_id(self):
        response = self.post(
            {"code": "ZAD-101"},
            telegram_user_id="not-a-number",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid Telegram user ID")

    def test_rejects_user_without_lookup_permission(self):
        user = self.telegram_user(
            can_receive_leads=True,
            can_lookup_products=False,
        )

        response = self.post(
            {"code": "ZAD-101"},
            telegram_user_id=user.telegram_user_id,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["error"],
            "Telegram user is not allowed",
        )

    def test_rejects_unknown_telegram_user(self):
        response = self.post(
            {"code": "ZAD-101"},
            telegram_user_id=987654321,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["error"],
            "Telegram user is not allowed",
        )

    def test_rejects_inactive_lookup_user(self):
        user = self.telegram_user(is_active=False)

        response = self.post(
            {"code": "ZAD-101"},
            telegram_user_id=user.telegram_user_id,
        )

        self.assertEqual(response.status_code, 403)

    def test_authorized_lookup_includes_nonpublic_products(self):
        user = self.telegram_user()
        valid_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            category = Category.objects.create(
                name="Internal lookup products",
                slug="internal-lookup-products",
                section=Category.Section.FLOWERS,
            )
            draft = Product.objects.create(
                name="Internal lookup draft",
                product_code="LOOKUP-DRAFT-001",
                category=category,
                publish_status=Product.PublishStatus.DRAFT,
                cover_image=SimpleUploadedFile(
                    "lookup-draft.png",
                    valid_png,
                    content_type="image/png",
                ),
            )
            inactive = Product.objects.create(
                name="Internal lookup inactive",
                product_code="LOOKUP-INACTIVE-002",
                category=category,
                publish_status=Product.PublishStatus.PUBLISHED,
                is_active=False,
                cover_image=SimpleUploadedFile(
                    "lookup-inactive.png",
                    valid_png,
                    content_type="image/png",
                ),
            )

            for product in (draft, inactive):
                with self.subTest(product_code=product.product_code):
                    response = self.post(
                        {"code": product.product_code},
                        telegram_user_id=user.telegram_user_id,
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response.json(),
                        {
                            "ok": True,
                            "product": {
                                "code": product.product_code,
                                "name": product.display_name,
                                "price_display": product.display_price,
                                "image_url": (
                                    f"http://testserver{product.cover_image.url}"
                                ),
                            },
                        },
                    )

    @patch("main.telegram_product_lookup.Product.objects.prefetch_related")
    def test_returns_product_and_first_image(self, prefetch_related):
        user = self.telegram_user()
        prefetch_related.return_value = self.product_query(self.product())

        response = self.post(
            {"code": "zad-101"},
            telegram_user_id=user.telegram_user_id,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "product": {
                    "code": "ZAD-101",
                    "name": "Test bouquet",
                    "price_display": "2,500,000 تومان",
                    "image_url": "http://testserver/media/products/zad-101.webp",
                },
            },
        )
        prefetch_related.assert_called_once_with("gallery_images")
        prefetch_related.return_value.filter.assert_called_once_with(
            product_code__iexact="zad-101"
        )

    @patch("main.telegram_product_lookup.Product.objects.prefetch_related")
    def test_returns_404_when_product_does_not_exist(self, prefetch_related):
        user = self.telegram_user()
        prefetch_related.return_value = self.product_query(None)

        response = self.post(
            {"code": "ZAD-404"},
            telegram_user_id=user.telegram_user_id,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Product not found")

    @patch("main.telegram_product_lookup.Product.objects.prefetch_related")
    def test_returns_404_when_product_has_no_image(self, prefetch_related):
        user = self.telegram_user()
        prefetch_related.return_value = self.product_query(
            self.product(gallery_image=False)
        )

        response = self.post(
            {"code": "ZAD-101"},
            telegram_user_id=user.telegram_user_id,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Product image not found")

    @patch("main.telegram_product_lookup.Product.objects.prefetch_related")
    def test_uses_cover_image_when_gallery_is_empty(self, prefetch_related):
        user = self.telegram_user()
        prefetch_related.return_value = self.product_query(
            self.product(gallery_image=False, cover_image=True)
        )

        response = self.post(
            {"code": "ZAD-101"},
            telegram_user_id=user.telegram_user_id,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["product"]["image_url"],
            "http://testserver/media/products/zad-101-cover.webp",
        )
