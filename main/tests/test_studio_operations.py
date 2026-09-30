import json
import tempfile
from django.core.files.base import ContentFile
from django.utils import timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from main.models import Category, Florist, Product, StudioIngestionIssue, StudioProduct, TelegramSameDayPost
from main.studio_ingestion import StudioInputError, parse_caption
from .test_telegram_same_day import GROUP, channel_post, image_file, sold_comment

CUSTOM_GROUP = -10087654


def custom_photo(caption="florist: mz\ntype: box\nfactor: 1234\nprice: 2400000", *, update_id=101):
    return {"update_id": update_id, "message": {
        "message_id": 730, "chat": {"id": CUSTOM_GROUP, "type": "supergroup"},
        "from": {"id": 666, "is_bot": False}, "date": 1700000000,
        "caption": caption, "photo": [{"file_id": "custom", "width": 100, "height": 100}],
    }}


class StudioParserTests(SimpleTestCase):
    def test_normalizes_field_names_and_persian_digits(self):
        self.assertEqual(parse_caption("FLORIST : MZ\nTYPE: box\nFACTOR: A-۱۲۳۴\nPRICE: ۲,۴۰۰,۰۰۰"), {
            "florist_code": "mz", "product_type": "box", "factor_code": "A-1234", "price": 2400000})

    def test_missing_duplicate_and_bad_values_rejected(self):
        for caption in ("florist: mz\ntype: box\nfactor: 1234",
                        "florist: mz\nflorist: ns\ntype: box\nfactor: 1234\nprice: 100",
                        "florist: mz\ntype: unknown\nfactor: 1234\nprice: 100",
                        "florist: mz\ntype: box\nfactor: 1234\nprice: 2.4m",
                        "florist: mz\ntype: box\nfactor: 1234\nprice: 0"):
            with self.subTest(caption=caption), self.assertRaises(StudioInputError):
                parse_caption(caption)


@override_settings(TELEGRAM_WEBHOOK_SECRET="test-secret", TELEGRAM_CHANNEL_ID="",
                   TELEGRAM_DISCUSSION_GROUP_ID="", TELEGRAM_SAME_DAY_GROUP_ID=str(GROUP),
                   TELEGRAM_STUDIO_CUSTOM_GROUP_ID=str(CUSTOM_GROUP),
                   TELEGRAM_SAME_DAY_RELAY_URL="", TELEGRAM_BOT_TOKEN="test-token")
class StudioIntegrationTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.category = Category.objects.create(name="گل", slug="studio-flowers", section="flowers")
        override = override_settings(TELEGRAM_SAME_DAY_CATEGORY_ID=str(self.category.pk))
        override.enable()
        self.addCleanup(override.disable)
        self.florist = Florist.objects.create(name="مهدی زعفری", code="mz")
        for path in ("main.studio_ingestion.download_photo", "main.telegram_same_day.service.download_photo"):
            mocker = patch(path, side_effect=image_file)
            mocker.start()
            self.addCleanup(mocker.stop)
        self.client = Client(enforce_csrf_checks=True)

    def send(self, update):
        return self.client.post(reverse("telegram_webhook"), json.dumps(update),
                                content_type="application/json",
                                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret")

    def daily(self, caption="florist: mz\ntype: box\nfactor: 1032\nقیمت: 2400000", **kwargs):
        update = channel_post(caption, **kwargs)
        kind = "edited_channel_post" if kwargs.get("edited") else "channel_post"
        update["message" if not kwargs.get("edited") else "edited_message"] = update.pop(kind)
        message = update["edited_message" if kwargs.get("edited") else "message"]
        message["chat"] = {"id": GROUP, "type": "supergroup"}
        message["from"] = {"id": 123, "is_bot": False}
        return update

    def test_custom_creates_only_ledger_and_duplicate_is_idempotent(self):
        update = custom_photo()
        response = self.send(update)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], "created")
        record = StudioProduct.objects.get()
        self.assertEqual((record.factor_code, record.price, record.production_type),
                         ("1234", 2400000, "CUSTOM"))
        self.assertTrue(record.image)
        self.assertFalse(Product.objects.exists())
        self.assertEqual(self.send(update).json()["result"], "duplicate_ignored")
        self.assertEqual(StudioProduct.objects.count(), 1)

    def test_invalid_messages_do_not_write_partial_records(self):
        for index, caption in enumerate(("florist: xx\ntype: box\nfactor: 1234\nprice: 2400000",
                                         "florist: mz\ntype: nope\nfactor: 1234\nprice: 2400000",
                                         "florist: mz\ntype: box\nfactor: 1234\nprice: nope")):
            update = custom_photo(caption, update_id=101 + index)
            update["message"]["message_id"] += index
            self.assertEqual(self.send(update).json()["result"], "rejected")
        self.assertFalse(StudioProduct.objects.exists())
        self.assertEqual(StudioIngestionIssue.objects.filter(resolved_at__isnull=True).count(), 3)
        self.florist.is_active = False
        self.florist.save()
        self.assertEqual(self.send(custom_photo()).json()["result"], "rejected")

    def test_invalid_custom_edit_resolves_existing_issue(self):
        self.send(custom_photo("florist: xx\ntype: box\nfactor: 1234\nprice: 2400000"))
        self.assertEqual(StudioIngestionIssue.objects.filter(resolved_at__isnull=True).count(), 1)
        update = custom_photo(update_id=111)
        update["edited_message"] = update.pop("message")
        update["edited_message"]["edit_date"] = 1700000004
        self.assertEqual(self.send(update).json()["result"], "created")
        self.assertEqual(StudioProduct.objects.count(), 1)
        self.assertEqual(StudioIngestionIssue.objects.filter(resolved_at__isnull=True).count(), 0)

    def test_custom_sold_reply_and_duplicate_factor(self):
        self.send(custom_photo())
        second = custom_photo(update_id=102)
        second["message"]["message_id"] = 731
        self.assertEqual(self.send(second).json()["result"], "rejected")
        reply = {"update_id": 103, "message": {"message_id": 740,
                 "chat": {"id": CUSTOM_GROUP, "type": "supergroup"},
                 "from": {"id": 666, "is_bot": False}, "date": 1700000001,
                 "text": "فروخته شد", "reply_to_message": custom_photo()["message"]}}
        self.assertEqual(self.send(reply).json()["result"], "status_updated")
        self.assertEqual(self.send(reply).json()["result"], "duplicate_ignored")
        record = StudioProduct.objects.get()
        self.assertEqual(record.status, "SOLD")
        self.assertIsNotNone(record.sold_at)

    def test_custom_price_reply_updates_ledger_and_returns_confirmation(self):
        self.send(custom_photo())
        reply = {"update_id": 113, "message": {"message_id": 742,
                 "chat": {"id": CUSTOM_GROUP, "type": "supergroup"},
                 "from": {"id": 666, "is_bot": False}, "date": 1700000003,
                 "text": "قیمت : 2500000", "reply_to_message": custom_photo()["message"]}}
        result = self.send(reply).json()
        self.assertEqual(result["result"], "price_updated")
        self.assertEqual(result["reply_to_message_id"], 742)
        self.assertIn("2,500,000 تومان", result["feedback"])
        record = StudioProduct.objects.get()
        self.assertEqual(record.price, 2500000)
        self.assertFalse(Product.objects.exists())

    def test_custom_edit_updates_price_without_duplicate(self):
        self.send(custom_photo())
        update = custom_photo("florist: mz\ntype: jar\nfactor: 1234\nprice: 3500000", update_id=109)
        update["edited_message"] = update.pop("message")
        update["edited_message"]["edit_date"] = 1700000100
        self.assertEqual(self.send(update).json()["result"], "updated")
        record = StudioProduct.objects.get()
        self.assertEqual((record.price, record.product_type), (3500000, "jar"))
        self.assertEqual(StudioProduct.objects.count(), 1)

    def test_invalid_image_and_sender_are_rejected(self):
        with patch("main.studio_ingestion.download_photo", return_value=ContentFile(b"not a photo", name="bad.jpg")):
            response = self.send(custom_photo())
        self.assertEqual(response.json()["result"], "rejected")
        self.assertFalse(StudioProduct.objects.exists())
        update = custom_photo()
        update["message"]["from"]["is_bot"] = True
        self.assertEqual(self.send(update).status_code, 403)

    def test_daily_sync_and_status_preserve_public_projection(self):
        self.send(self.daily())
        record = StudioProduct.objects.get()
        self.assertIsNotNone(record.product_id)
        self.assertEqual(record.price, 2400000)
        self.assertEqual(Product.objects.count(), 1)
        reply = sold_comment(reply=self.daily()["message"], text="کشیده شد", update_id=104)
        reply["message"]["chat"] = {"id": GROUP, "type": "supergroup"}
        reply["message"]["from"] = {"id": 123, "is_bot": False}
        self.send(reply)
        record.refresh_from_db()
        self.assertEqual(record.status, "WITHDRAWN")
        self.assertEqual(record.product.status, Product.Status.WITHDRAWN)

    def test_daily_price_and_photo_snapshot_survive_product_deletion(self):
        self.send(self.daily())
        record = StudioProduct.objects.get()
        image_name = record.image.name
        self.assertTrue(image_name)
        product = record.product
        product.price = 2700000
        product.save()
        record.refresh_from_db()
        self.assertEqual(record.price, 2700000)
        product.delete()
        record.refresh_from_db()
        self.assertIsNone(record.product_id)
        self.assertEqual(record.image.name, image_name)
        self.assertEqual(record.status, StudioProduct.Status.CANCELLED)

    def test_late_group_price_completes_metadata(self):
        update = self.daily("florist: mz\ntype: box\nfactor: 1234")
        self.send(update)
        self.assertFalse(StudioProduct.objects.exists())
        reply = {"update_id": 110, "message": {"message_id": 741,
                 "chat": {"id": GROUP, "type": "supergroup"},
                 "from": {"id": 123, "is_bot": False}, "date": 1700000002,
                 "text": "۲۴۰۰", "reply_to_message": update["message"]}}
        self.assertEqual(self.send(reply).json()["result"], "created")
        self.assertEqual(StudioProduct.objects.get().factor_code, "1234")

    def test_legacy_and_strict_cutover(self):
        self.send(self.daily("قیمت: 2400000"))
        self.assertEqual(Product.objects.count(), 1)
        self.assertFalse(StudioProduct.objects.exists())
        self.assertTrue(TelegramSameDayPost.objects.get().studio_error)
        with override_settings(STUDIO_DAILY_REQUIRE_METADATA=True):
            update = self.daily("قیمت: 2500000", update_id=105)
            update["message"]["message_id"] = 71
            self.assertEqual(self.send(update).json()["result"], "studio_metadata_rejected")
        self.assertEqual(Product.objects.count(), 1)

    def test_dashboard_is_private_and_uses_real_cohort(self):
        self.assertEqual(self.client.get(reverse("studio_dashboard")).status_code, 302)
        user = get_user_model().objects.create_superuser(username="studio-admin", password="pass")
        self.client.force_login(user)
        response = self.client.get(reverse("studio_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stats"]["produced"], 0)
        self.send(custom_photo())
        response = self.client.get(reverse("studio_dashboard"))
        # The fixture's Telegram timestamp is historical and outside today's period.
        self.assertEqual(response.context["stats"]["produced"], 0)
        record = StudioProduct.objects.get()
        record.produced_at = timezone.now()
        record.save(update_fields=["produced_at"])
        response = self.client.get(reverse("studio_dashboard"))
        self.assertEqual(response.context["stats"]["produced"], 1)
        self.assertContains(response, "1234")
        listing = self.client.get(reverse("studio_products"), {"q": "1234"})
        self.assertEqual(listing.context["summary"]["produced"], 1)
        self.assertEqual(listing.context["page"].paginator.count, 1)
        filtered_out = self.client.get(reverse("studio_products"), {"q": "NO-SUCH-FACTOR"})
        self.assertEqual(filtered_out.context["summary"]["produced"], 0)
        for name in ("studio_products", "studio_florists", "studio_analytics", "studio_settings"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(reverse("studio_florist_profile", args=[self.florist.pk])).status_code, 200)

    def test_manual_product_and_florist_management(self):
        user = get_user_model().objects.create_superuser(username="studio-editor", password="pass")
        self.client.force_login(user)
        self.client.get(reverse("studio_florist_add"))
        csrf = {"HTTP_X_CSRFTOKEN": self.client.cookies["csrftoken"].value}
        response = self.client.post(reverse("studio_florist_add"), {
            "name": "نیوشا", "code": "ns", "is_active": "on", "joined_at": "2026-09-26"}, **csrf)
        self.assertEqual(response.status_code, 302)
        florist = Florist.objects.get(code="ns")
        self.client.post(reverse("studio_florist_edit", args=[florist.pk]), {
            "name": "نیوشا", "code": "ns", "joined_at": "2026-09-26", "left_at": "2026-09-27"}, **csrf)
        florist.refresh_from_db()
        self.assertFalse(florist.is_active)
        image = image_file()
        response = self.client.post(reverse("studio_product_add"), {
            "image": image, "florist": self.florist.pk, "factor_code": "ZAD-5001",
            "product_type": "box", "production_type": "CUSTOM", "price": "2400000",
            "status": "AVAILABLE", "notes": "ثبت دستی",
        }, **csrf)
        self.assertEqual(response.status_code, 302)
        record = StudioProduct.objects.get(factor_code="ZAD-5001")
        self.assertEqual(record.created_by, user)
        self.assertEqual(record.source, StudioProduct.Source.DASHBOARD)
        self.assertFalse(Product.objects.exists())
        response = self.client.post(reverse("studio_product_edit", args=[record.pk]), {
            "florist": self.florist.pk, "factor_code": "ZAD-5001", "product_type": "jar",
            "production_type": "CUSTOM", "price": "2600000", "notes": "اصلاح دستی",
        }, **csrf)
        self.assertEqual(response.status_code, 302)
        record.refresh_from_db()
        self.assertEqual((record.price, record.product_type), (2600000, "jar"))
        response = self.client.post(reverse("studio_product_status", args=[record.pk]), {"status": "SOLD"}, **csrf)
        self.assertEqual(response.status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.status, "SOLD")
        self.assertIsNotNone(record.sold_at)
        self.assertEqual(self.client.get(reverse("studio_product_edit", args=[record.pk])).status_code, 403)
