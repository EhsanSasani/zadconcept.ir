import copy
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from PIL import Image

from main.models import Category, Product, SameDayFlower, TelegramBotUser, TelegramDiscussionMessage, TelegramSameDayPost
from main.telegram_same_day.client import TelegramTransportError, download_photo
from main.telegram_same_day.price import PriceError, parse_price

CHANNEL = -10012345
GROUP = -10054321
SETTINGS = dict(
    TELEGRAM_WEBHOOK_SECRET="test-secret", TELEGRAM_CHANNEL_ID=str(CHANNEL),
    TELEGRAM_DISCUSSION_GROUP_ID=str(GROUP), TELEGRAM_SAME_DAY_CATEGORY_ID="1",
    TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_SAME_DAY_RELAY_URL="",
)


def channel_post(price="قیمت: ۲,۸۵۰,۰۰۰ تومان", *, update_id=10, message_id=70, edited=False):
    message = {
        "message_id": message_id, "chat": {"id": CHANNEL, "type": "channel"},
        "date": 1700000000, "caption": price,
        "photo": [{"file_id": "small", "width": 20, "height": 20},
                  {"file_id": "large", "width": 100, "height": 100}],
    }
    if edited:
        message["edit_date"] = 1700000001
    return {"update_id": update_id, "edited_channel_post" if edited else "channel_post": message}


def root_message():
    return {
        "message_id": 500, "chat": {"id": GROUP, "type": "supergroup"},
        "date": 1700000000, "is_automatic_forward": True,
        "forward_origin": {"type": "channel", "chat": {"id": CHANNEL, "type": "channel"},
                           "message_id": 70, "date": 1700000000},
    }


def sold_comment(*, sender=123, reply=None, text="فروخته شد", message_id=501, update_id=20):
    return {"update_id": update_id, "message": {
        "message_id": message_id, "date": 1700000002,
        "chat": {"id": GROUP, "type": "supergroup"},
        "from": {"id": sender, "is_bot": False}, "text": text,
        "reply_to_message": reply if reply is not None else root_message(),
    }}


def image_file(*args):
    data = BytesIO()
    Image.new("RGB", (100, 100), "pink").save(data, "JPEG")
    return ContentFile(data.getvalue(), name="telegram.jpg")


class PriceParserTests(SimpleTestCase):
    def test_supported_prices(self):
        for caption in ("۲,۸۵۰,۰۰۰", "2,850,000", "۲/۸۵۰/۰۰۰", "قیمت ۲۸۵۰۰۰۰",
                        "قیمت: ۲,۸۵۰,۰۰۰ تومان", "قیمت: ٢٬٨٥٠٬٠٠٠ تومان",
                        "دسته گل رز\nقیمت: ۲,۸۵۰,۰۰۰ تومان"):
            with self.subTest(caption=caption):
                self.assertEqual(parse_price(caption), 2850000)
                self.assertIsInstance(parse_price(caption), int)

    def test_ambiguous_and_invalid_prices_fail_closed(self):
        for caption in ("گل رز", "تماس 09123456789", "قیمت توافقی", "قیمت 2,85,000",
                        "قیمت: -200", "قیمت: 2.85 میلیون", "قیمت ۰", "1\n2",
                        "قیمت 100 ریال", "قیمت 1000000000000", "قیمت 100\nقیمت 100",
                        "قیمت 100 یا 200", "قیمت 100 دلار", None):
            with self.subTest(caption=caption):
                with self.assertRaises(PriceError):
                    parse_price(caption)


@override_settings(**SETTINGS)
class SameDayWebhookTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.category = Category.objects.create(name="گل", slug="test-flowers", section="flowers")
        category_override = override_settings(TELEGRAM_SAME_DAY_CATEGORY_ID=str(self.category.pk))
        category_override.enable()
        self.addCleanup(category_override.disable)
        self.operator = TelegramBotUser.objects.create(name="اپراتور", telegram_user_id=123, can_manage_same_day=True)
        downloader = patch("main.telegram_same_day.service.download_photo", side_effect=image_file)
        self.download = downloader.start()
        self.addCleanup(downloader.stop)
        self.client = Client(enforce_csrf_checks=True)

    def send(self, update, secret="test-secret"):
        return self.client.post(reverse("telegram_webhook"), data=json.dumps(update),
                                content_type="application/json",
                                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret)

    def product(self):
        return Product.objects.get(catalog_scope=Product.CatalogScope.SAME_DAY)

    def test_valid_channel_post_uses_existing_catalog_and_image_pipeline(self):
        response = self.send(channel_post())
        self.assertEqual(response.status_code, 200)
        product = self.product()
        post = product.telegram_same_day_post
        self.assertEqual(product.price, 2850000)
        self.assertEqual(product.pricing_type, Product.PricingType.FIXED)
        self.assertEqual(product.publish_status, Product.PublishStatus.PUBLISHED)
        self.assertEqual(product.status, Product.Status.AVAILABLE)
        self.assertEqual(post.telegram_chat_id, CHANNEL)
        self.assertEqual(post.telegram_message_id, 70)
        self.assertIsNotNone(post.telegram_created_at)
        self.download.assert_called_once_with("large")
        self.assertTrue(product.cover_image.name.endswith(".webp"))
        self.assertTrue(product.cover_image.storage.exists(product.cover_image.name))
        self.assertTrue(SameDayFlower.objects.filter(pk=product.pk).exists())
        self.assertContains(self.client.get(reverse("flowers_same_day")), product.product_code)
        self.assertFalse(Product.objects.for_general_catalog().filter(pk=product.pk).exists())

    def test_retry_is_idempotent_without_image_download(self):
        update = channel_post()
        self.send(update)
        response = self.send(update)
        self.assertEqual(response.json()["result"], "duplicate_ignored")
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(TelegramSameDayPost.objects.count(), 1)
        self.download.assert_called_once()

    def test_same_message_in_new_update_cannot_duplicate_product(self):
        self.send(channel_post())
        self.send(channel_post(update_id=11))
        self.assertEqual(Product.objects.count(), 1)
        self.download.assert_called_once()

    def test_english_caption(self):
        self.send(channel_post("2,850,000"))
        self.assertEqual(self.product().price, 2850000)

    def test_no_price_is_logged_and_never_published(self):
        with self.assertLogs("main.telegram_same_day", level="WARNING") as logs:
            response = self.send(channel_post("گل آماده"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.exists())
        self.assertTrue(TelegramSameDayPost.objects.get().last_error)
        self.download.assert_not_called()
        self.assertIn("price parsing failed", logs.output[0])
        self.assertIn("message_id=70", logs.output[0])

    def test_edited_caption_updates_same_product_without_download(self):
        self.send(channel_post())
        original = self.product()
        response = self.send(channel_post("قیمت 3000000", update_id=12, edited=True))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.product().pk, original.pk)
        self.assertEqual(self.product().price, 3000000)
        self.download.assert_called_once()

    def test_edit_arrives_before_original_and_stale_retry_cannot_revert_price(self):
        self.send(channel_post("3000000", update_id=12, edited=True))
        self.send(channel_post())
        self.assertEqual(self.product().price, 3000000)
        self.download.assert_called_once()

    def test_invalid_edit_hides_product_until_corrected(self):
        self.send(channel_post())
        self.send(channel_post("قیمت توافقی", update_id=12, edited=True))
        self.assertFalse(Product.objects.for_same_day().published().exists())
        self.send(channel_post("4000000", update_id=13, edited=True))
        self.assertEqual(self.product().price, 4000000)
        self.assertTrue(Product.objects.for_same_day().published().exists())
        self.download.assert_called_once()

    def test_album_is_not_partially_published(self):
        update = channel_post()
        update["channel_post"]["media_group_id"] = "album"
        self.send(update)
        self.assertFalse(Product.objects.exists())
        self.download.assert_not_called()

    def test_group_comment_marks_sold_and_hides_all_public_selections(self):
        self.send(channel_post())
        product = self.product()
        response = self.send(sold_comment())
        self.assertEqual(response.json()["result"], "sold")
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.SOLD)
        self.assertEqual(product.stock_status, Product.StockStatus.OUT_OF_STOCK)
        self.assertEqual(Product.objects.count(), 1)
        self.assertTrue(SameDayFlower.objects.filter(pk=product.pk).exists())
        self.assertFalse(Product.objects.for_same_day().published().exists())
        self.assertNotContains(self.client.get(reverse("flowers_same_day")), product.product_code)
        home = self.client.get(reverse("index"))
        self.assertFalse(home.context["home_same_day_products"].filter(pk=product.pk).exists())
        self.assertFalse(Product.objects.publicly_indexable().filter(pk=product.pk).exists())
        self.assertEqual(self.send(sold_comment()).json()["result"], "duplicate_ignored")

    def test_channel_reply_marks_sold(self):
        post = channel_post()
        self.send(post)
        reply = {"update_id": 11, "channel_post": {
            "message_id": 71, "chat": {"id": CHANNEL, "type": "channel"},
            "date": 1700000001, "text": "فروخته شد", "reply_to_message": post["channel_post"],
        }}
        self.assertEqual(self.send(reply).status_code, 200)
        self.assertEqual(self.product().status, Product.Status.SOLD)

    def test_price_edit_never_reopens_sold_product(self):
        self.send(channel_post())
        self.send(sold_comment())
        self.send(channel_post("3000000", update_id=30, edited=True))
        self.assertEqual(self.product().price, 3000000)
        self.assertEqual(self.product().status, Product.Status.SOLD)

    def test_group_forward_and_sold_before_channel_post(self):
        self.send({"update_id": 9, "message": root_message()})
        self.send(sold_comment())
        self.assertFalse(Product.objects.exists())
        self.send(channel_post())
        self.assertEqual(self.product().status, Product.Status.SOLD)
        self.assertFalse(Product.objects.for_same_day().published().exists())

    def test_nested_reply_uses_persisted_identity(self):
        self.send(channel_post())
        first = sold_comment(text="چه زیبا", sender=999)
        self.send(first)
        reply = copy.deepcopy(first["message"])
        reply.pop("reply_to_message")
        self.send(sold_comment(reply=reply, message_id=502, update_id=21))
        self.assertEqual(self.product().status, Product.Status.SOLD)
        self.assertEqual(TelegramDiscussionMessage.objects.count(), 3)

    def test_thread_id_fallback_only_uses_verified_root(self):
        self.send(channel_post())
        self.send({"update_id": 11, "message": root_message()})
        update = sold_comment(reply={"message_id": 999, "chat": {"id": GROUP, "type": "supergroup"}})
        update["message"]["message_thread_id"] = 500
        self.send(update)
        self.assertEqual(self.product().status, Product.Status.SOLD)

    def test_unknown_reply_ignored(self):
        update = sold_comment(reply={"message_id": 999, "chat": {"id": GROUP, "type": "supergroup"}})
        self.assertEqual(self.send(update).json()["result"], "unknown_reply_ignored")
        self.assertFalse(Product.objects.exists())

    def test_wrong_source_cannot_create_or_sell(self):
        update = channel_post()
        update["channel_post"]["chat"]["id"] = -999
        self.assertEqual(self.send(update).status_code, 403)
        self.download.assert_not_called()
        self.send(channel_post())
        update = sold_comment()
        update["message"]["chat"]["id"] = -999
        self.assertEqual(self.send(update).status_code, 403)
        self.assertEqual(self.product().status, Product.Status.AVAILABLE)

    def test_regular_member_disabled_operator_anonymous_and_bot_cannot_sell(self):
        self.send(channel_post())
        updates = [sold_comment(sender=999), sold_comment()]
        updates[1]["message"]["sender_chat"] = {"id": GROUP}
        bot = sold_comment()
        bot["message"]["from"]["is_bot"] = True
        updates.append(bot)
        for update in updates:
            self.assertEqual(self.send(update).status_code, 403)
        self.operator.is_active = False
        self.operator.save()
        self.assertEqual(self.send(sold_comment()).status_code, 403)
        self.assertEqual(self.product().status, Product.Status.AVAILABLE)

    def test_manual_forward_is_not_a_discussion_root(self):
        self.send(channel_post())
        root = root_message()
        root.pop("is_automatic_forward")
        self.assertEqual(self.send(sold_comment(reply=root)).json()["result"], "unknown_reply_ignored")
        self.assertEqual(self.product().status, Product.Status.AVAILABLE)

    def test_foreign_channel_origin_is_not_trusted(self):
        self.send(channel_post())
        root = root_message()
        root["forward_origin"]["chat"]["id"] = -999
        self.send(sold_comment(reply=root))
        self.assertEqual(self.product().status, Product.Status.AVAILABLE)

    def test_forwarded_sold_text_is_not_an_action(self):
        self.send(channel_post())
        update = sold_comment()
        update["message"]["forward_origin"] = {"type": "user"}
        self.assertEqual(self.send(update).status_code, 403)
        self.assertEqual(self.product().status, Product.Status.AVAILABLE)

    def test_bad_secret_and_missing_configuration_fail_closed(self):
        self.assertEqual(self.send(channel_post(), secret="wrong").status_code, 403)
        self.assertEqual(self.send(channel_post(), secret="رمز").status_code, 403)
        with override_settings(TELEGRAM_WEBHOOK_SECRET=""):
            self.assertEqual(self.send(channel_post(), secret="").status_code, 403)
        with override_settings(TELEGRAM_SAME_DAY_CATEGORY_ID=""):
            self.assertEqual(self.send(channel_post()).status_code, 503)
        self.download.assert_not_called()

    def test_invalid_payloads_rejected_without_database_or_network(self):
        bad_photo = channel_post()
        bad_photo["channel_post"]["photo"] = [None]
        bad_origin = sold_comment()
        bad_origin["message"]["reply_to_message"]["forward_origin"]["chat"] = []
        for update in ([], None, {}, {"update_id": True}, bad_photo, bad_origin):
            self.assertEqual(self.send(update).status_code, 400)
        self.assertFalse(Product.objects.exists())
        self.download.assert_not_called()
        response = self.client.post(reverse("telegram_webhook"), data="{", content_type="application/json",
                                    HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(reverse("telegram_webhook")).status_code, 405)
        self.assertEqual(self.send({"update_id": 1, "unused": "x" * 131072}).status_code, 400)

    def test_download_failure_is_retryable_and_does_not_consume_update(self):
        self.download.side_effect = TelegramTransportError("token must not appear")
        with self.assertLogs("main.telegram_same_day", level="ERROR") as logs:
            self.assertEqual(self.send(channel_post()).status_code, 503)
        self.assertNotIn("token must not appear", " ".join(logs.output))
        self.assertFalse(Product.objects.exists())
        self.assertFalse(TelegramSameDayPost.objects.exists())
        self.download.side_effect = image_file
        self.assertEqual(self.send(channel_post()).status_code, 200)
        self.assertEqual(Product.objects.count(), 1)

    def test_corrupt_image_never_published(self):
        self.download.side_effect = lambda *args: ContentFile(b"not an image", name="bad.jpg")
        self.assertEqual(self.send(channel_post()).status_code, 200)
        self.assertFalse(Product.objects.exists())
        self.assertEqual(TelegramSameDayPost.objects.get().last_error, "invalid_image")

    def test_new_image_on_edit_replaces_cover(self):
        self.send(channel_post())
        update = channel_post(edited=True, update_id=12)
        update["edited_channel_post"]["photo"][-1]["file_id"] = "replacement"
        self.send(update)
        self.assertEqual(self.product().telegram_same_day_post.telegram_file_id, "replacement")
        self.assertEqual(self.download.call_count, 2)

    def test_admin_created_same_day_products_remain_compatible(self):
        manual = Product.objects.create(category=self.category, catalog_scope="same_day", publish_status="published")
        self.assertEqual(manual.status, Product.Status.AVAILABLE)
        self.assertTrue(Product.objects.for_same_day().published().filter(pk=manual.pk).exists())
        self.send(channel_post())
        self.send(sold_comment())
        self.assertTrue(Product.objects.for_same_day().published().filter(pk=manual.pk).exists())

    def test_database_failure_after_image_save_cleans_new_media(self):
        from pathlib import Path
        original_save = TelegramSameDayPost.save

        def fail_after_image(instance, *args, **kwargs):
            if instance.product_id:
                raise OSError("simulated write failure")
            return original_save(instance, *args, **kwargs)

        with patch.object(TelegramSameDayPost, "save", autospec=True, side_effect=fail_after_image):
            self.assertEqual(self.send(channel_post()).status_code, 503)
        self.assertFalse(Product.objects.exists())
        self.assertFalse(TelegramSameDayPost.objects.exists())
        self.assertEqual(list(Path(self.media.name).rglob("*.webp")), [])

    def test_database_enforces_post_identity(self):
        self.send(channel_post())
        with self.assertRaises(IntegrityError), transaction.atomic():
            TelegramSameDayPost.objects.create(telegram_chat_id=CHANNEL, telegram_message_id=70)


@override_settings(**SETTINGS)
class TelegramClientTests(SimpleTestCase):
    @patch("main.telegram_same_day.client._request")
    def test_direct_get_file_downloads_bytes(self, request):
        request.side_effect = [json.dumps({"ok": True, "result": {"file_path": "photos/file_1.jpg"}}).encode(), b"image"]
        self.assertEqual(download_photo("file-id").read(), b"image")
        self.assertEqual(request.call_count, 2)

    @patch("main.telegram_same_day.client._request")
    def test_file_path_cannot_be_arbitrary_url_or_traversal(self, request):
        for path in ("https://evil.example/x", "../x.jpg", "/x.jpg", "photos/../../x.jpg"):
            request.return_value = json.dumps({"ok": True, "result": {"file_path": path}}).encode()
            with self.assertRaises(TelegramTransportError):
                download_photo("file-id")
        self.assertEqual(request.call_count, 4)

    @override_settings(TELEGRAM_SAME_DAY_RELAY_URL="https://relay.example", TELEGRAM_LEAD_RELAY_SECRET="relay-secret", TELEGRAM_BOT_TOKEN="")
    @patch("main.telegram_same_day.client._request", return_value=b"image")
    def test_worker_download_needs_no_bot_token_in_django(self, request):
        self.assertEqual(download_photo("file-id").read(), b"image")
        self.assertEqual(request.call_args.args[0], "https://relay.example/same-day-file")
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer relay-secret")

    @patch("main.telegram_same_day.client.build_opener")
    def test_oversized_download_rejected(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.read.return_value = b"x" * 11
        from main.telegram_same_day.client import _request
        with self.assertRaises(TelegramTransportError):
            _request("https://example.test/image", limit=10)


@override_settings(**SETTINGS)
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def test_parallel_duplicate_delivery_downloads_once(self):
        if connection.vendor != "postgresql":
            self.skipTest("Requires PostgreSQL row locking; SQLite does not implement select_for_update")
        category = Category.objects.create(name="گل", slug="parallel-flowers", section="flowers")
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media, TELEGRAM_SAME_DAY_CATEGORY_ID=str(category.pk)), patch(
            "main.telegram_same_day.service.download_photo", side_effect=image_file
        ) as download:
            def deliver(_):
                close_old_connections()
                try:
                    response = Client().post(reverse("telegram_webhook"), data=json.dumps(channel_post()),
                                             content_type="application/json",
                                             HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret")
                    return response.status_code
                finally:
                    close_old_connections()
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(list(pool.map(deliver, range(2))), [200, 200])
            self.assertEqual(Product.objects.filter(category=category).count(), 1)
            download.assert_called_once()


@override_settings(**SETTINGS)
class WebhookCommandTests(SimpleTestCase):
    @patch("main.management.commands.telegram_same_day_webhook.bot_api", return_value=True)
    def test_register_keeps_pending_updates_and_subscribes_to_edits(self, api):
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command("telegram_same_day_webhook", "register", url="https://relay.example/telegram-webhook", stdout=out)
        method, payload = api.call_args.args
        self.assertEqual(method, "setWebhook")
        self.assertFalse(payload["drop_pending_updates"])
        self.assertEqual(payload["max_connections"], 1)
        self.assertIn("edited_channel_post", payload["allowed_updates"])
        self.assertNotIn("test-secret", out.getvalue())

    @patch("main.management.commands.telegram_same_day_webhook.bot_api")
    def test_register_rejects_insecure_url(self, api):
        from django.core.management import call_command, CommandError
        with self.assertRaises(CommandError):
            call_command("telegram_same_day_webhook", "register", url="http://example.com")
        api.assert_not_called()
