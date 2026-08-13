import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings


@override_settings(TELEGRAM_LEAD_RELAY_SECRET="test-relay-secret")
class TelegramProductLookupTests(SimpleTestCase):
    url = "/internal/telegram/product-lookup/"

    def post(self, payload, *, authorized=True):
        headers = {}
        if authorized:
            headers["HTTP_AUTHORIZATION"] = "Bearer test-relay-secret"
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def product(self, *, with_image=True):
        images = []
        if with_image:
            images.append(
                SimpleNamespace(
                    image=SimpleNamespace(url="/media/products/zad-101.webp")
                )
            )
        return SimpleNamespace(
            product_code="ZAD-101",
            display_name="Test bouquet",
            gallery_images=SimpleNamespace(all=lambda: images),
        )

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
        response = self.post({"code": ""})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid product code")

    @patch("main.telegram_product_lookup.Product.objects.prefetch_related")
    def test_returns_product_and_first_image(self, prefetch_related):
        prefetch_related.return_value = self.product_query(self.product())

        response = self.post({"code": "zad-101"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "product": {
                    "code": "ZAD-101",
                    "name": "Test bouquet",
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
        prefetch_related.return_value = self.product_query(None)

        response = self.post({"code": "ZAD-404"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Product not found")

    @patch("main.telegram_product_lookup.Product.objects.prefetch_related")
    def test_returns_404_when_product_has_no_image(self, prefetch_related):
        prefetch_related.return_value = self.product_query(
            self.product(with_image=False)
        )

        response = self.post({"code": "ZAD-101"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Product image not found")
