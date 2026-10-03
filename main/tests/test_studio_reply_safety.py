"""Regression coverage for live replies, deletion history and delayed updates."""
import copy
import tempfile
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.query import QuerySet
from django.test import TestCase, override_settings
from django.utils import timezone

from main.models import (
    Category, Florist, Product, StudioDelivery, StudioProduct, TelegramSameDayPost,
)
from main.studio_delivery import (
    claim_delivery, process_next_delivery, product_caption, soft_delete_product,
)
from main.studio_ingestion import sync_daily_status
from main.studio_publishing import create_portal_record
from main.telegram_same_day.service import SyncConfigurationError, process_update
from .test_telegram_same_day import image_file


DAILY_GROUP = -100775501
CUSTOM_GROUP = -100775502


@override_settings(
    STUDIO_ADMIN_NOTIFICATIONS_ENABLED=True,
    TELEGRAM_CHANNEL_ID="", TELEGRAM_DISCUSSION_GROUP_ID="",
    TELEGRAM_SAME_DAY_GROUP_ID=str(DAILY_GROUP),
    TELEGRAM_STUDIO_CUSTOM_GROUP_ID=str(CUSTOM_GROUP),
    TELEGRAM_STUDIO_ADMIN_CHAT_ID="212832276",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class StudioReplySafetyTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.category = Category.objects.create(
            name="گل", slug="reply-safety", section=Category.Section.FLOWERS,
        )
        config = override_settings(
            MEDIA_ROOT=media.name,
            TELEGRAM_SAME_DAY_CATEGORY_ID=str(self.category.pk),
        )
        config.enable()
        self.addCleanup(config.disable)
        self.user = get_user_model().objects.create_user("reply-florist")
        self.manager = get_user_model().objects.create_superuser("reply-manager")
        self.florist = Florist.objects.create(
            name="آزمایش", code="rs", user=self.user,
        )
        self.clock = int(timezone.now().timestamp())
        self.message_count = 0
        self.record_count = 0
        # All outbound and download boundaries stay local. These tests must
        # remain safe even if real Telegram credentials exist in the environment.
        self.send = self._patch("main.studio_transport.send_photo", side_effect=self._sent_photo)
        self.delete = self._patch("main.studio_transport.delete_message", return_value=True)
        self.edit = self._patch("main.studio_transport.edit_caption", return_value=True)
        self.daily_download = self._patch(
            "main.telegram_same_day.service.download_photo", side_effect=image_file,
        )
        self.custom_download = self._patch(
            "main.studio_ingestion.download_photo", side_effect=image_file,
        )

    def _patch(self, path, **kwargs):
        mocker = patch(path, **kwargs)
        result = mocker.start()
        self.addCleanup(mocker.stop)
        return result

    def _sent_photo(self, chat_id, *args):
        self.message_count += 1
        return {
            "message_id": 1000 + self.message_count,
            "chat": {"id": chat_id, "type": "supergroup"},
            "date": self.clock,
            "from": {"id": 99, "is_bot": True},
            "photo": [{"file_id": "sent-photo", "width": 100, "height": 100}],
        }

    def _portal_record(self, production_type="DAILY", *, publish=True):
        self.record_count += 1
        record, _ = create_portal_record(
            user=self.user, florist=self.florist, image=image_file(),
            factor_code=f"RS-{self.record_count}", product_type="box",
            production_type=production_type, price=2400000,
            submission_key=uuid.uuid4(),
        )
        if publish:
            for _ in range(10):
                job = process_next_delivery()
                self.assertIsNotNone(job)
                if job.record_id == record.pk and job.action == StudioDelivery.Action.PUBLISH:
                    break
            else:
                self.fail("The new record's publish job was not processed.")
            self.assertEqual(job.status, StudioDelivery.Status.SENT)
            record.refresh_from_db()
        return record

    def _reply(self, record, text, *, seconds=10, message_id=None):
        chat_id = DAILY_GROUP if record.production_type == "DAILY" else CUSTOM_GROUP
        original = {
            "message_id": record.telegram_message_id or 1001,
            "chat": {"id": chat_id, "type": "supergroup"},
            "date": self.clock, "caption": product_caption(record),
            "from": {"id": 99, "is_bot": True},
            "photo": [{"file_id": "sent-photo", "width": 100, "height": 100}],
        }
        return {
            "message_id": message_id or 2000 + record.pk * 100 + seconds,
            "date": self.clock + seconds,
            "chat": {"id": chat_id, "type": "supergroup"},
            "from": {"id": 702, "is_bot": False}, "text": text,
            "reply_to_message": original,
        }

    def _legacy_photo(self, production_type):
        chat_id = DAILY_GROUP if production_type == "DAILY" else CUSTOM_GROUP
        message = {
            "message_id": 3000, "date": self.clock,
            "chat": {"id": chat_id, "type": "supergroup"},
            "from": {"id": 702, "is_bot": False},
            "caption": "florist: rs\ntype: box\nfactor: LEGACY-1\nقیمت: 2400000",
            "photo": [{"file_id": "legacy-photo", "width": 100, "height": 100}],
        }
        process_update("message", message, 100)
        return StudioProduct.objects.get(
            telegram_chat_id=chat_id, telegram_message_id=3000,
        ), message

    def _deleted_snapshot(self, record):
        record = soft_delete_product(record, actor=self.manager, reason="ثبت آزمایشی اشتباه")
        self.assertEqual(record.status, StudioProduct.Status.DELETED)
        self.assertEqual(record.deleted_by_id, self.manager.pk)
        self.assertIsNotNone(record.deleted_at)
        return self._snapshot(record)

    @staticmethod
    def _snapshot(record):
        record.refresh_from_db()
        return {
            name: getattr(record, name)
            for name in (
                "status", "price", "factor_code", "florist_id", "product_type",
                "telegram_file_id", "revision_date", "revision_update_id",
                "sold_at", "withdrawn_at", "deleted_at", "deleted_by_id",
                "deletion_reason",
            )
        } | {"image": record.image.name}

    def test_deleted_daily_portal_replies_preserve_audit_and_catalog(self):
        record = self._portal_record()
        snapshot = self._deleted_snapshot(record)
        notifications = record.admin_notifications.count()
        for index, text in enumerate(("قیمت: 3500000", "فروخته شد", "کشیده شد")):
            with self.subTest(text=text):
                process_update("message", self._reply(record, text, seconds=10 + index), 200 + index)
                self.assertEqual(self._snapshot(record), snapshot)
                self.assertEqual(record.admin_notifications.count(), notifications)
                product = Product.objects.get(pk=record.product_id)
                self.assertEqual(product.price, snapshot["price"])
                self.assertFalse(Product.objects.published().filter(pk=product.pk).exists())

    def test_deleted_custom_portal_replies_preserve_audit(self):
        record = self._portal_record("CUSTOM")
        snapshot = self._deleted_snapshot(record)
        notifications = record.admin_notifications.count()
        for index, text in enumerate(("قیمت: 3500000", "فروخته شد", "کشیده شد")):
            with self.subTest(text=text):
                process_update("message", self._reply(record, text, seconds=10 + index), 200 + index)
                self.assertEqual(self._snapshot(record), snapshot)
                self.assertEqual(record.admin_notifications.count(), notifications)

    def test_deleted_legacy_daily_photo_edit_cannot_change_retained_history(self):
        record, photo = self._legacy_photo("DAILY")
        snapshot = self._deleted_snapshot(record)
        photo["edit_date"] = self.clock + 20
        photo["caption"] = photo["caption"].replace("2400000", "3500000")
        photo["photo"][0]["file_id"] = "replacement-photo"
        downloads = self.daily_download.call_count
        process_update("edited_message", photo, 200)
        self.assertEqual(self._snapshot(record), snapshot)
        self.assertEqual(self.daily_download.call_count, downloads)
        product = Product.objects.get(pk=record.product_id)
        self.assertEqual(product.price, snapshot["price"])
        self.assertFalse(Product.objects.published().filter(pk=product.pk).exists())

    def test_deleted_legacy_custom_photo_edit_and_price_preserve_history(self):
        record, photo = self._legacy_photo("CUSTOM")
        snapshot = self._deleted_snapshot(record)
        photo["edit_date"] = self.clock + 20
        photo["caption"] = photo["caption"].replace("2400000", "3500000")
        photo["photo"][0]["file_id"] = "replacement-photo"
        downloads = self.custom_download.call_count
        process_update("edited_message", photo, 200)
        process_update("message", self._reply(record, "قیمت: 4500000", seconds=30), 201)
        self.assertEqual(self._snapshot(record), snapshot)
        self.assertEqual(self.custom_download.call_count, downloads)

    def test_prepatch_deleted_daily_row_without_post_tombstone_stays_immutable(self):
        record, photo = self._legacy_photo("DAILY")
        snapshot = self._deleted_snapshot(record)
        # The previous deployed soft-delete service only wrote withdrawn_at.
        # Preserve protection for those rows without requiring a data rewrite.
        TelegramSameDayPost.objects.filter(product_id=record.product_id).update(deleted_at=None)
        product = Product.objects.get(pk=record.product_id)
        public_snapshot = (product.price, product.cover_image.name)
        photo["edit_date"] = self.clock + 20
        photo["caption"] = photo["caption"].replace("2400000", "3500000")
        photo["photo"][0]["file_id"] = "replacement-photo"
        downloads = self.daily_download.call_count
        process_update("edited_message", photo, 200)
        self.assertEqual(self._snapshot(record), snapshot)
        self.assertEqual(self.daily_download.call_count, downloads)
        product.refresh_from_db()
        self.assertEqual((product.price, product.cover_image.name), public_snapshot)

    def test_daily_status_sync_cannot_replace_deleted_with_withdrawn(self):
        record = self._portal_record()
        snapshot = self._deleted_snapshot(record)
        post = TelegramSameDayPost.objects.get(product_id=record.product_id)
        sync_daily_status(post)
        self.assertEqual(self._snapshot(record), snapshot)

    def test_custom_immediate_reply_is_retryable_until_identity_is_mapped(self):
        record = self._portal_record("CUSTOM", publish=False)
        job = claim_delivery()
        for status in (StudioDelivery.Status.SENDING, StudioDelivery.Status.UNCERTAIN):
            StudioDelivery.objects.filter(pk=job.pk).update(status=status)
            for text in ("فروخته شد", "کشیده شد", "قیمت: 3500000"):
                with self.subTest(status=status, text=text), self.assertRaises(SyncConfigurationError):
                    process_update("message", self._reply(record, text), 200)
        record.refresh_from_db()
        self.assertEqual(record.status, StudioProduct.Status.AVAILABLE)
        self.assertEqual(record.price, 2400000)

    def test_unknown_custom_bot_photo_is_not_matched_by_an_unrelated_caption(self):
        record = self._portal_record("CUSTOM", publish=False)
        claim_delivery()
        reply = self._reply(record, "فروخته شد")
        reply["reply_to_message"]["caption"] = "قیمت: 999999\nفاکتور: unrelated"
        result = process_update("message", reply, 200)
        self.assertEqual(result["result"], "unknown_reply_ignored")
        record.refresh_from_db()
        self.assertEqual(record.status, StudioProduct.Status.AVAILABLE)

    def _assert_old_caption_during_pending_price_change_is_retryable(self, production_type):
        record = self._portal_record(production_type, publish=False)
        claim_delivery()
        # The outgoing request already captured its original legitimate caption.
        reply = self._reply(record, "فروخته شد")
        record.price = 3500000
        record.save(update_fields=["price", "updated_at"])
        with self.assertRaises(SyncConfigurationError):
            process_update("message", reply, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, StudioProduct.Status.AVAILABLE)
        self.assertEqual(record.price, 3500000)
        self.assertIsNone(record.telegram_message_id)

    def test_pending_daily_sale_with_old_caption_defers_after_price_change(self):
        self._assert_old_caption_during_pending_price_change_is_retryable("DAILY")

    def test_pending_custom_sale_with_old_caption_defers_after_price_change(self):
        self._assert_old_caption_during_pending_price_change_is_retryable("CUSTOM")

    def test_pending_custom_same_factor_in_non_outbound_caption_is_not_matched(self):
        record = self._portal_record("CUSTOM", publish=False)
        claim_delivery()
        for caption in (
            f"پیام دیگر\nفاکتور: {record.factor_code}",
            f"{product_caption(record)}\nمتن اضافی",
            f"قیمت: نامعتبر تومان\nفاکتور: {record.factor_code}",
        ):
            with self.subTest(caption=caption):
                reply = self._reply(record, "فروخته شد")
                reply["reply_to_message"]["caption"] = caption
                result = process_update("message", reply, 200)
                self.assertEqual(result["result"], "unknown_reply_ignored")
        record.refresh_from_db()
        self.assertEqual(record.status, StudioProduct.Status.AVAILABLE)
        self.assertIsNone(record.telegram_message_id)

    def test_custom_reply_rereads_mapping_when_initial_lookup_misses_commit(self):
        record = self._portal_record("CUSTOM")
        original_filter = QuerySet.filter
        missed = False

        def miss_first_identity_lookup(queryset, *args, **kwargs):
            nonlocal missed
            if (not missed and queryset.model is StudioProduct
                    and kwargs.get("telegram_chat_id") == CUSTOM_GROUP
                    and kwargs.get("telegram_message_id") == record.telegram_message_id):
                missed = True
                return original_filter(queryset, pk__in=[])
            return original_filter(queryset, *args, **kwargs)

        with patch.object(QuerySet, "filter", new=miss_first_identity_lookup):
            result = process_update("message", self._reply(record, "فروخته شد"), 200)
        self.assertTrue(missed)
        self.assertEqual(result["result"], "status_updated")
        record.refresh_from_db()
        self.assertEqual(record.status, StudioProduct.Status.SOLD)
        self.assertTrue(record.deliveries.filter(action=StudioDelivery.Action.RETIRE).exists())

    def _assert_price_ordering(self, production_type):
        record = self._portal_record(production_type)
        fresh = self._reply(record, "قیمت: 3500000", seconds=20, message_id=2010)
        older = self._reply(record, "قیمت: 2800000", seconds=10, message_id=2005)
        process_update("message", fresh, 200)
        notifications = record.admin_notifications.count()
        process_update("message", older, 150)
        record.refresh_from_db()
        self.assertEqual(record.price, 3500000)
        process_update("message", fresh, 200)
        record.refresh_from_db()
        self.assertEqual(record.price, 3500000)
        self.assertEqual(record.admin_notifications.count(), notifications)
        if record.product_id:
            self.assertEqual(Product.objects.get(pk=record.product_id).price, 3500000)
        edited = copy.deepcopy(older)
        edited["edit_date"] = self.clock + 30
        edited["text"] = "قیمت: 3900000"
        process_update("edited_message", edited, 220)
        # A delayed retry of the previously fresh command must not undo an edit.
        process_update("message", fresh, 200)
        record.refresh_from_db()
        self.assertEqual(record.price, 3900000)
        if record.product_id:
            self.assertEqual(Product.objects.get(pk=record.product_id).price, 3900000)

    def test_daily_explicit_price_reply_and_edit_reject_older_replays(self):
        self._assert_price_ordering("DAILY")

    def test_custom_explicit_price_reply_and_edit_reject_older_replays(self):
        self._assert_price_ordering("CUSTOM")

    def test_legacy_daily_old_photo_cannot_undo_a_later_explicit_price_reply(self):
        record, photo = self._legacy_photo("DAILY")
        reply = self._reply(record, "قیمت: 3500000", seconds=20)
        process_update("message", reply, 200)
        photo["edit_date"] = self.clock + 10
        photo["caption"] = photo["caption"].replace("2400000", "2800000")
        process_update("edited_message", photo, 150)
        record.refresh_from_db()
        self.assertEqual(record.price, 3500000)
        self.assertEqual(Product.objects.get(pk=record.product_id).price, 3500000)

    def test_legacy_custom_old_photo_cannot_undo_a_later_explicit_price_reply(self):
        record, photo = self._legacy_photo("CUSTOM")
        reply = self._reply(record, "قیمت: 3500000", seconds=20)
        process_update("message", reply, 200)
        photo["edit_date"] = self.clock + 10
        photo["caption"] = photo["caption"].replace("2400000", "2800000")
        process_update("edited_message", photo, 150)
        record.refresh_from_db()
        self.assertEqual(record.price, 3500000)

    def test_normal_daily_and_custom_price_then_sale_or_withdrawal_still_work(self):
        for production_type in ("DAILY", "CUSTOM"):
            for text, status in (("فروخته شد", "SOLD"), ("کشیده شد", "WITHDRAWN")):
                with self.subTest(production_type=production_type, status=status):
                    record = self._portal_record(production_type)
                    result = process_update("message", self._reply(record, "قیمت: 3500000"), 200)
                    self.assertEqual(result["result"], "price_updated")
                    process_update("message", self._reply(record, text, seconds=20), 220)
                    record.refresh_from_db()
                    self.assertEqual(record.price, 3500000)
                    self.assertEqual(record.status, status)
                    self.assertTrue(record.deliveries.filter(action=StudioDelivery.Action.RETIRE).exists())
                    if record.product_id:
                        product = Product.objects.get(pk=record.product_id)
                        self.assertEqual(product.price, 3500000)
                        self.assertEqual(product.stock_status, Product.StockStatus.OUT_OF_STOCK)
