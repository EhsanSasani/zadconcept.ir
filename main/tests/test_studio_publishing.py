import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone

from main.models import Category, Florist, Product, StudioDelivery, StudioProduct, TelegramSameDayPost
from main.studio_delivery import (
    claim_delivery, delivery_summary, process_next_delivery, product_caption,
    reconcile_delivery, retry_delivery, retry_uncertain_delivery, set_portal_status,
)
from main.studio_publishing import create_portal_record
from main.studio_transport import TelegramDeliveryError
from main.telegram_same_day.service import SyncConfigurationError, process_update
from .test_telegram_same_day import image_file

GROUP = -100887711


@override_settings(TELEGRAM_SAME_DAY_GROUP_ID=str(GROUP), TELEGRAM_CHANNEL_ID="",
                   TELEGRAM_DISCUSSION_GROUP_ID="", TELEGRAM_STUDIO_CUSTOM_GROUP_ID="-5182713369")
class StudioPublishingTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.category = Category.objects.create(name="گل", slug="portal-flowers", section="flowers")
        config = override_settings(MEDIA_ROOT=self.media.name, TELEGRAM_SAME_DAY_CATEGORY_ID=str(self.category.pk))
        config.enable()
        self.addCleanup(config.disable)
        self.user = get_user_model().objects.create_user("portal-florist", password="test-password")
        self.manager = get_user_model().objects.create_superuser("portal-manager", password="test-password")
        self.florist = Florist.objects.create(name="آزمایش", code="portal", user=self.user)
        # Every outbound boundary is mocked. No test can contact a live group.
        self.send = patch("main.studio_transport.send_photo", side_effect=self.telegram_message).start()
        self.delete = patch("main.studio_transport.delete_message", return_value=True).start()
        self.edit = patch("main.studio_transport.edit_caption", return_value=True).start()
        self.addCleanup(patch.stopall)

    def telegram_message(self, *args):
        return {"message_id": 812, "chat": {"id": args[0] if args else GROUP, "type": "supergroup"},
                "date": int(timezone.now().timestamp()), "from": {"id": 99, "is_bot": True},
                "photo": [{"file_id": "uploaded", "width": 500, "height": 500}]}

    def create(self, **overrides):
        values = dict(user=self.user, florist=self.florist, image=image_file(), factor_code="PORTAL-123",
                      product_type="box", production_type="DAILY", price=2400000, submission_key=uuid.uuid4())
        values.update(overrides)
        return create_portal_record(**values)

    def publish(self):
        record, _ = self.create()
        job = process_next_delivery()
        self.assertEqual(job.status, StudioDelivery.Status.SENT)
        record.refresh_from_db()
        return record, job

    def sold_reply(self, record, *, text="فروخته شد"):
        reply = self.telegram_message()
        reply["caption"] = product_caption(record)
        return {"message_id": 815, "chat": {"id": GROUP, "type": "supergroup"},
                "date": int(timezone.now().timestamp()), "from": {"id": 702, "is_bot": False},
                "text": text, "reply_to_message": reply}

    def test_daily_registration_is_public_immediately_and_network_is_deferred(self):
        record, created = self.create(notes="فقط برای استودیو")
        self.assertTrue(created)
        self.assertTrue(Product.objects.for_same_day().published().filter(pk=record.product_id).exists())
        self.assertEqual(record.product.cover_image.name, record.image.name)
        self.assertEqual(record.product.price, record.price)
        self.assertNotIn(record.factor_code, record.product.name)
        self.assertNotIn(record.notes, record.product.description)
        self.assertEqual(record.source, "PORTAL")
        self.assertEqual(record.created_by, self.user)
        self.assertEqual(record.deliveries.get().status, "PENDING")
        self.send.assert_not_called()

    def test_custom_queues_its_own_group_without_daily_configuration(self):
        with override_settings(TELEGRAM_SAME_DAY_CATEGORY_ID="", TELEGRAM_SAME_DAY_GROUP_ID=""):
            record, _ = self.create(production_type="CUSTOM")
        self.assertIsNone(record.product_id)
        self.assertFalse(Product.objects.exists())
        self.assertEqual(record.deliveries.get().chat_id, -5182713369)
        self.assertEqual(delivery_summary(record)["state"], "pending")
        self.assertIn("سفارشی‌ها", delivery_summary(record)["label"])
        self.send.assert_not_called()
        job = process_next_delivery()
        self.assertEqual(job.status, StudioDelivery.Status.SENT)
        record.refresh_from_db()
        self.assertEqual(record.telegram_chat_id, -5182713369)
        self.assertFalse(TelegramSameDayPost.objects.exists())
        self.assertIn("سفارشی‌ها", delivery_summary(record)["label"])
        self.assertEqual(self.send.call_args.args[2], product_caption(record))

    def test_custom_configuration_failure_leaves_no_upload_or_record(self):
        for group in ("", "123", str(GROUP)):
            with self.subTest(group=group), override_settings(TELEGRAM_STUDIO_CUSTOM_GROUP_ID=group):
                with patch("main.studio_publishing.normalize_admin_image") as normalize:
                    with self.assertRaises(ValidationError):
                        self.create(production_type="CUSTOM")
                    normalize.assert_not_called()
        self.assertFalse(StudioProduct.objects.exists())
        self.assertFalse(StudioDelivery.objects.exists())

    def test_custom_repeated_submission_does_not_duplicate_delivery(self):
        key = uuid.uuid4()
        record, _ = self.create(production_type="CUSTOM", submission_key=key)
        second, created = self.create(production_type="CUSTOM", submission_key=key, image=None)
        self.assertEqual(record.pk, second.pk)
        self.assertFalse(created)
        self.assertEqual(StudioDelivery.objects.count(), 1)
        self.assertFalse(Product.objects.exists())

    def test_custom_portal_reply_retires_message_without_public_product(self):
        record, _ = self.create(production_type="CUSTOM")
        process_next_delivery()
        record.refresh_from_db()
        message = self.sold_reply(record)
        message["chat"]["id"] = -5182713369
        message["reply_to_message"]["chat"]["id"] = -5182713369
        self.assertEqual(process_update("message", message, 901)["result"], "status_updated")
        record.refresh_from_db()
        self.assertEqual(record.status, StudioProduct.Status.SOLD)
        job = process_next_delivery()
        self.assertEqual(job.action, StudioDelivery.Action.RETIRE)
        self.assertEqual(job.status, StudioDelivery.Status.SENT)
        self.delete.assert_called_once_with(-5182713369, 812)
        self.assertFalse(Product.objects.exists())

    def test_custom_portal_photo_edits_do_not_reimport_minimal_caption(self):
        record, _ = self.create(production_type="CUSTOM")
        process_next_delivery()
        message = self.telegram_message(-5182713369)
        message["caption"] = product_caption(record)
        message["from"] = {"id": 702, "is_bot": False}
        result = process_update("edited_message", message, 902)
        self.assertEqual(result["result"], "portal_message_ignored")
        self.assertEqual(StudioProduct.objects.count(), 1)

    def test_same_key_retries_return_existing_without_new_image_or_send(self):
        key = uuid.uuid4()
        record, _ = self.create(submission_key=key)
        second, created = self.create(submission_key=key, image=None, price=999, factor_code="CHANGED")
        self.assertFalse(created)
        self.assertEqual(record.pk, second.pk)
        self.assertEqual(second.price, 2400000)
        self.assertEqual(StudioProduct.objects.count(), 1)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(StudioDelivery.objects.count(), 1)

    def test_key_collision_from_other_actor_does_not_disclose_record(self):
        record, _ = self.create()
        other = get_user_model().objects.create_user("other-florist")
        florist = Florist.objects.create(name="دیگر", code="other", user=other)
        with self.assertRaises(ValidationError) as error:
            self.create(user=other, florist=florist, submission_key=record.submission_key)
        self.assertIn("submission_key", error.exception.message_dict)
        self.assertNotIn(record.factor_code, str(error.exception))

    def test_florist_identity_and_active_assignment_are_rechecked(self):
        other = get_user_model().objects.create_user("unlinked")
        with self.assertRaises(PermissionDenied):
            self.create(user=other)
        Florist.objects.filter(pk=self.florist.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.create()

    def test_selected_maker_is_separate_from_authenticated_submitter(self):
        maker = Florist.objects.create(name="همکار فعال", code="maker")
        record, _ = self.create(florist=maker, production_type="CUSTOM")
        self.assertEqual(record.florist, maker)
        self.assertEqual(record.created_by, self.user)
        self.assertEqual(record.deliveries.get().chat_id, -5182713369)

    def test_selected_florist_deactivated_after_form_read_is_rejected(self):
        maker = Florist.objects.create(name="همکار", code="maker")
        Florist.objects.filter(pk=maker.pk).update(is_active=False)
        with self.assertRaises(ValidationError) as error:
            self.create(florist=maker)
        self.assertIn("florist", error.exception.message_dict)
        self.assertFalse(StudioProduct.objects.exists())

    def test_selected_florist_deactivation_during_upload_leaves_no_records(self):
        from main.image_pipeline import normalize_admin_image
        maker = Florist.objects.create(name="همکار", code="maker")

        def normalize_and_deactivate(image):
            result = normalize_admin_image(image)
            Florist.objects.filter(pk=maker.pk).update(is_active=False)
            return result

        with patch("main.studio_publishing.normalize_admin_image", side_effect=normalize_and_deactivate):
            with self.assertRaises(ValidationError) as error:
                self.create(florist=maker)
        self.assertIn("florist", error.exception.message_dict)
        self.assertFalse(StudioProduct.objects.exists())
        self.assertFalse(Product.objects.exists())
        self.assertFalse(StudioDelivery.objects.exists())

    def test_bad_configuration_or_duplicate_invoice_leaves_no_extra_records(self):
        with override_settings(TELEGRAM_SAME_DAY_CATEGORY_ID=""):
            with self.assertRaises(ValidationError):
                self.create()
        self.assertFalse(StudioProduct.objects.exists())
        self.create(factor_code="A-۱۲۳")
        with self.assertRaises(ValidationError):
            self.create(factor_code="a-123")
        self.assertEqual(StudioProduct.objects.get().factor_code, "A-123")

    def test_failed_public_projection_rolls_back_rows_and_new_media(self):
        with patch("main.studio_publishing.Product.objects.create", side_effect=IntegrityError("forced")):
            with self.assertRaises(ValidationError):
                self.create()
        self.assertFalse(StudioProduct.objects.exists())
        self.assertFalse(StudioDelivery.objects.exists())
        self.assertFalse([path for path in Path(self.media.name).rglob("*") if path.is_file()])

    def test_publish_sends_only_photo_price_invoice_and_maps_identity(self):
        record, job = self.publish()
        args = self.send.call_args.args
        self.assertEqual(args[0], GROUP)
        self.assertTrue(args[1].startswith(b"\xff\xd8\xff"))
        self.assertEqual(args[2], "قیمت: 2,400,000 تومان\nفاکتور: PORTAL-123")
        post = TelegramSameDayPost.objects.get()
        self.assertEqual(post.product_id, record.product_id)
        self.assertEqual((record.telegram_chat_id, record.telegram_message_id), (GROUP, 812))
        self.assertEqual(job.message_id, 812)
        self.assertIsNone(process_next_delivery())
        self.send.assert_called_once()

    def test_any_human_group_member_sale_retires_message_and_keeps_history_media(self):
        record, _ = self.publish()
        result = process_update("message", self.sold_reply(record), 911)
        self.assertEqual(result, "sold")
        record.refresh_from_db()
        self.assertEqual(record.status, StudioProduct.Status.SOLD)
        self.assertFalse(Product.objects.for_same_day().published().filter(pk=record.product_id).exists())
        self.assertTrue(record.image.storage.exists(record.image.name))
        self.assertEqual(process_next_delivery().outcome, "deleted")
        self.delete.assert_called_once_with(GROUP, 812)
        self.edit.assert_not_called()
        self.assertEqual(process_update("message", self.sold_reply(record), 912), "duplicate_ignored")
        self.assertEqual(StudioDelivery.objects.filter(action="RETIRE").count(), 1)

    def test_withdrawal_also_hides_site_and_enqueues_retirement(self):
        record, _ = self.publish()
        self.assertEqual(process_update("message", self.sold_reply(record, text="کشیده شد"), 914), "withdrawn")
        record.refresh_from_db()
        self.assertEqual(record.status, "WITHDRAWN")
        self.assertEqual(record.product.status, "WITHDRAWN")
        self.assertTrue(record.deliveries.filter(action="RETIRE").exists())

    def test_old_messages_use_caption_fallback_without_delete(self):
        record, _ = self.publish()
        record.deliveries.update(telegram_created_at=timezone.now() - timedelta(hours=49))
        set_portal_status(record, "SOLD", actor=self.manager)
        job = process_next_delivery()
        self.assertEqual(job.outcome, "caption_marked")
        self.delete.assert_not_called()
        self.assertEqual(self.edit.call_args.args[2], "فروخته شد\nقیمت: 2,400,000 تومان\nفاکتور: PORTAL-123")

    def test_permanent_delete_error_uses_caption_fallback(self):
        record, _ = self.publish()
        set_portal_status(record, "WITHDRAWN", actor=self.manager)
        self.delete.side_effect = TelegramDeliveryError("message_cannot_be_deleted")
        self.assertEqual(process_next_delivery().outcome, "caption_marked")
        self.assertTrue(self.edit.call_args.args[2].startswith("کشیده شد\n"))

    def test_retryable_delete_failure_does_not_claim_success(self):
        record, _ = self.publish()
        set_portal_status(record, "SOLD", actor=self.manager)
        self.delete.side_effect = TelegramDeliveryError("rate_limited", retryable=True, retry_after=75)
        before = timezone.now()
        job = process_next_delivery()
        self.assertEqual(job.status, "RETRY")
        self.assertGreaterEqual(job.next_attempt_at, before + timedelta(seconds=75))
        self.edit.assert_not_called()

    def test_missing_old_message_is_already_retired(self):
        record, _ = self.publish()
        record.deliveries.update(telegram_created_at=timezone.now() - timedelta(hours=49))
        set_portal_status(record, "SOLD", actor=self.manager)
        self.edit.side_effect = TelegramDeliveryError("message_not_found")
        self.assertEqual(process_next_delivery().outcome, "already_absent")

    def test_ambiguous_send_is_visible_and_never_blindly_retried(self):
        record, _ = self.create()
        self.send.side_effect = TelegramDeliveryError("transport_uncertain", uncertain=True)
        job = process_next_delivery()
        self.assertEqual(job.status, "UNCERTAIN")
        self.assertEqual(delivery_summary(record)["state"], "uncertain")
        self.assertIsNone(process_next_delivery())
        with self.assertRaises(ValidationError):
            retry_delivery(job.pk)
        self.send.assert_called_once()
        reconciled = reconcile_delivery(job.pk, 899)
        self.assertEqual(reconciled.status, "SENT")
        record.refresh_from_db()
        self.assertEqual(record.telegram_message_id, 899)
        self.send.assert_called_once()

    def test_definite_failure_can_be_retried_after_configuration_repaired(self):
        self.create()
        self.send.side_effect = TelegramDeliveryError("configuration_error")
        job = process_next_delivery()
        self.assertEqual(job.status, "FAILED")
        retry_delivery(job.pk)
        self.send.side_effect = self.telegram_message
        self.assertEqual(process_next_delivery().status, "SENT")

    def test_manual_uncertain_retry_requires_manager_confirmation_and_expired_lease(self):
        self.create()
        self.send.side_effect = TelegramDeliveryError("transport_uncertain", uncertain=True)
        job = process_next_delivery()
        with self.assertRaises(PermissionDenied):
            retry_uncertain_delivery(job.pk, actor=self.user, confirmed_absent=True)
        for confirmation in [False, "true", 1]:
            with self.assertRaises(ValidationError):
                retry_uncertain_delivery(job.pk, actor=self.manager, confirmed_absent=confirmation)
        with self.assertRaises(ValidationError):
            retry_uncertain_delivery(job.pk, actor=self.manager, confirmed_absent=True)
        StudioDelivery.objects.filter(pk=job.pk).update(locked_at=timezone.now() - timedelta(minutes=5))
        result = retry_uncertain_delivery(job.pk, actor=self.manager, confirmed_absent=True)
        self.assertEqual(result.status, "PENDING")
        self.assertEqual(result.manual_retry_by, self.manager)
        self.assertIsNotNone(result.manual_retry_at)
        self.assertIsNone(result.lock_token)
        with self.assertRaises(ValidationError):
            retry_uncertain_delivery(job.pk, actor=self.manager, confirmed_absent=True)
        self.send.side_effect = self.telegram_message
        self.assertEqual(process_next_delivery().status, "SENT")
        result.refresh_from_db()
        self.assertEqual(result.manual_retry_by, self.manager)

    def test_manual_uncertain_retry_rejects_mapped_message(self):
        record, job = self.publish()
        StudioDelivery.objects.filter(pk=job.pk).update(status="UNCERTAIN")
        with self.assertRaises(ValidationError):
            retry_uncertain_delivery(job.pk, actor=self.manager, confirmed_absent=True)
        self.send.assert_called_once()

    def test_malformed_success_is_uncertain_and_reconcile_rejects_other_product_message(self):
        first, _ = self.publish()
        second, _ = self.create(factor_code="PORTAL-456")
        self.send.side_effect = None
        self.send.return_value = {"message_id": 44, "chat": {"id": -1}, "date": 1}
        job = process_next_delivery()
        self.assertEqual(job.status, "UNCERTAIN")
        with self.assertRaises(ValidationError):
            reconcile_delivery(job.pk, first.telegram_message_id)
        second.refresh_from_db()
        self.assertIsNone(second.telegram_message_id)

    def test_stale_retirement_can_retry_without_republishing(self):
        record, _ = self.publish()
        set_portal_status(record, "SOLD", actor=self.manager)
        retirement = claim_delivery()
        StudioDelivery.objects.filter(pk=retirement.pk).update(locked_at=timezone.now() - timedelta(minutes=5))
        self.assertEqual(process_next_delivery().outcome, "deleted")
        self.send.assert_called_once()

    def test_caption_fallback_failure_remains_visible(self):
        record, _ = self.publish()
        set_portal_status(record, "SOLD", actor=self.manager)
        self.delete.side_effect = TelegramDeliveryError("forbidden")
        self.edit.side_effect = TelegramDeliveryError("forbidden")
        job = process_next_delivery()
        self.assertEqual(job.status, "FAILED")
        self.assertEqual(delivery_summary(record)["state"], "failed")
        self.assertTrue(record.image.storage.exists(record.image.name))

    def test_stale_publish_lease_becomes_uncertain_but_retirement_is_retryable(self):
        self.create()
        job = claim_delivery()
        StudioDelivery.objects.filter(pk=job.pk).update(locked_at=timezone.now() - timedelta(minutes=5))
        self.assertIsNone(process_next_delivery())
        job.refresh_from_db()
        self.assertEqual(job.status, "UNCERTAIN")
        self.send.assert_not_called()

    def test_paused_worker_does_not_send_after_its_lease_expires(self):
        record, _ = self.create()
        def expire_lease(_record):
            record.deliveries.update(locked_at=timezone.now() - timedelta(minutes=5))
            return b"jpeg"
        with patch("main.studio_delivery._jpeg_bytes", side_effect=expire_lease):
            process_next_delivery()
        self.assertIsNone(process_next_delivery())
        self.assertEqual(record.deliveries.get().status, "UNCERTAIN")
        self.send.assert_not_called()

    def test_claim_is_exclusive_and_send_before_saved_response_failure_is_uncertain(self):
        self.create()
        job = claim_delivery()
        self.assertIsNone(claim_delivery())
        StudioDelivery.objects.filter(pk=job.pk).update(status="PENDING", lock_token=None)
        with patch("main.studio_delivery._map_message", side_effect=IntegrityError("lost save")):
            result = process_next_delivery()
        self.assertEqual(result.status, "UNCERTAIN")
        self.assertIsNone(process_next_delivery())

    def test_status_before_send_prevents_post_and_sale_during_send_retires_it(self):
        record, _ = self.create()
        set_portal_status(record, "CANCELLED", actor=self.manager)
        self.assertEqual(process_next_delivery().outcome, "not_available")
        self.send.assert_not_called()
        record, _ = self.create(factor_code="PORTAL-124")
        def sell_in_flight(*args):
            set_portal_status(record, "SOLD", actor=self.manager)
            return self.telegram_message()
        self.send.side_effect = sell_in_flight
        self.assertEqual(process_next_delivery().status, "SENT")
        self.assertTrue(record.deliveries.filter(action="RETIRE").exists())

    def test_immediate_reply_before_send_mapping_remains_retryable(self):
        record, _ = self.create()
        claim_delivery()
        with self.assertRaises(SyncConfigurationError):
            process_update("message", self.sold_reply(record), 917)
        self.assertFalse(TelegramSameDayPost.objects.exists())

    def test_reply_rereads_identity_if_worker_commits_between_lookups(self):
        record, _ = self.publish()
        original_filter = TelegramSameDayPost.objects.filter
        missed = False
        def miss_first_identity_lookup(*args, **kwargs):
            nonlocal missed
            if not missed and kwargs == {"telegram_chat_id": GROUP, "telegram_message_id": 812}:
                missed = True
                return TelegramSameDayPost.objects.none()
            return original_filter(*args, **kwargs)
        with patch.object(TelegramSameDayPost.objects, "filter", side_effect=miss_first_identity_lookup):
            self.assertEqual(process_update("message", self.sold_reply(record), 922), "sold")
        record.refresh_from_db()
        self.assertEqual(record.status, "SOLD")

    def test_status_change_during_caption_fallback_is_queued_again(self):
        record, _ = self.publish()
        record.deliveries.update(telegram_created_at=timezone.now() - timedelta(hours=49))
        set_portal_status(record, "SOLD", actor=self.manager)
        def withdraw_during_caption(*args):
            self.assertEqual(process_update("message", self.sold_reply(record, text="کشیده شد"), 924), "withdrawn")
            return True
        self.edit.side_effect = withdraw_during_caption
        self.assertEqual(process_next_delivery().status, "RETRY")
        self.edit.side_effect = None
        self.assertEqual(process_next_delivery().outcome, "caption_marked")
        self.assertTrue(self.edit.call_args.args[2].startswith("کشیده شد\n"))

    def test_portal_photo_echo_and_unrelated_reply_never_enter_legacy_parser(self):
        record, _ = self.publish()
        echo = self.telegram_message()
        echo["caption"] = product_caption(record)
        self.assertEqual(process_update("message", echo, 919), "portal_echo_ignored")
        self.assertEqual(process_update("message", self.sold_reply(record, text="قیمت: 999"), 920), "portal_reply_ignored")
        record.product.refresh_from_db()
        self.assertEqual(record.product.price, 2400000)
        self.assertEqual(record.product.publish_status, "published")

    def test_status_requires_manager_permission_and_preserves_terminal_history(self):
        record, _ = self.create()
        with self.assertRaises(PermissionDenied):
            set_portal_status(record, "SOLD", actor=self.user)
        record = set_portal_status(record, "SOLD", actor=self.manager)
        self.assertEqual(set_portal_status(record, "SOLD", actor=self.manager).status, "SOLD")
        with self.assertRaises(ValidationError):
            set_portal_status(record, "AVAILABLE", actor=self.manager)
        with self.assertRaises(ValidationError):
            set_portal_status(record, "WITHDRAWN", actor=self.manager)
