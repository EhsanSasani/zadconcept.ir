import tempfile
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from main.models import Florist, StudioAdminNotification, StudioProduct
from main.studio_admin_notifications import (
    claim_admin_notification, process_next_admin_notification,
    reconcile_admin_notification, retry_admin_notification,
)
from main.studio_transport import TelegramDeliveryError, get_chat
from .test_telegram_same_day import image_file


@override_settings(
    TELEGRAM_STUDIO_ADMIN_CHAT_ID="212832276", TELEGRAM_SAME_DAY_GROUP_ID="-5595039112",
    TELEGRAM_STUDIO_CUSTOM_GROUP_ID="-5182713369", TELEGRAM_BOT_TOKEN="test-token",
    TELEGRAM_SAME_DAY_RELAY_URL="", STUDIO_DELIVERY_LOCK_SECONDS=120,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class NotificationSafetyTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        config = override_settings(MEDIA_ROOT=media.name)
        config.enable()
        self.addCleanup(config.disable)
        self.manager = get_user_model().objects.create_superuser("notification-manager")
        self.user = get_user_model().objects.create_user("notification-maker")
        self.florist = Florist.objects.create(name="آزمایش", code="n-test", user=self.user)
        mocker = patch("main.studio_transport.send_photo", return_value={"message_id": 77, "chat": {"id": 212832276}})
        self.send = mocker.start()
        self.addCleanup(mocker.stop)

    def create(self, factor="N-123"):
        return StudioProduct.objects.create(florist=self.florist, created_by=self.manager,
            factor_code=factor, product_type="box", production_type="CUSTOM", price=2500000,
            image=image_file(), source="DASHBOARD")

    def uncertain(self, row):
        job = row.admin_notifications.get()
        job.status = "UNCERTAIN"
        job.locked_at = timezone.now() - timedelta(minutes=3)
        job.lock_token = uuid.uuid4()
        job.last_error = "transport_uncertain"
        job.save()
        return job

    def test_missing_image_does_not_stop_group_processing(self):
        bad = self.create()
        good = self.create("N-124")
        bad.image.storage.delete(bad.image.name)
        stdout = StringIO()
        with patch("main.management.commands.process_studio_deliveries.process_next_delivery", return_value=None) as group:
            call_command("process_studio_deliveries", once=True, limit=5, stdout=stdout)
        self.assertGreaterEqual(group.call_count, 3)
        self.assertEqual(bad.admin_notifications.get().status, "FAILED")
        self.assertEqual(good.admin_notifications.get().status, "SENT")
        self.send.assert_called_once()

    def test_corrupt_image_is_known_failure_before_network(self):
        row = self.create()
        with row.image.storage.open(row.image.name, "wb") as file:
            file.write(b"not an image")
        self.assertEqual(process_next_admin_notification().status, "FAILED")
        self.send.assert_not_called()

    def test_malformed_success_is_uncertain_not_retried(self):
        self.create()
        self.send.return_value = {}
        self.assertEqual(process_next_admin_notification().status, "UNCERTAIN")
        self.assertIsNone(process_next_admin_notification())
        self.send.assert_called_once()

    def test_stale_lease_cannot_send_after_photo_processing(self):
        row = self.create()
        def photo(record):
            row.admin_notifications.update(locked_at=timezone.now() - timedelta(minutes=3))
            return b"jpeg"
        with patch("main.studio_admin_notifications._jpeg_bytes", side_effect=photo):
            process_next_admin_notification()
        self.send.assert_not_called()
        self.assertIsNone(claim_admin_notification())
        self.assertEqual(row.admin_notifications.get().status, "UNCERTAIN")

    def test_revoked_lease_cannot_send_or_finish(self):
        row = self.create()
        def photo(record):
            row.admin_notifications.update(status="PENDING", lock_token=None, locked_at=None)
            return b"jpeg"
        with patch("main.studio_admin_notifications._jpeg_bytes", side_effect=photo):
            job = process_next_admin_notification()
        self.assertEqual(job.status, "PENDING")
        self.send.assert_not_called()

    def test_retry_waits_before_later_price_for_same_product(self):
        row = self.create()
        first = row.admin_notifications.get()
        first.status, first.next_attempt_at = "RETRY", timezone.now() + timedelta(hours=1)
        first.save()
        row.price = 2800000
        row.save(update_fields=["price", "updated_at"])
        self.assertIsNone(claim_admin_notification())
        # Another product's messages still progress independently.
        other = self.create("N-125")
        self.assertEqual(process_next_admin_notification().record_id, other.pk)

    def test_uncertain_prior_event_blocks_later_event(self):
        row = self.create()
        self.uncertain(row)
        row.price = 2800000
        row.save(update_fields=["price", "updated_at"])
        self.assertIsNone(claim_admin_notification())

    def test_failed_known_event_does_not_block_current_notification(self):
        row = self.create()
        row.admin_notifications.update(status="FAILED")
        row.price = 2800000
        row.save(update_fields=["price", "updated_at"])
        self.assertEqual(process_next_admin_notification().event, "PRICE")

    def test_manual_retry_is_audited_and_double_click_cannot_duplicate(self):
        row = self.create()
        row.admin_notifications.update(status="FAILED", last_error="invalid_payload")
        job = row.admin_notifications.get()
        retry_admin_notification(job.pk, actor=self.manager)
        self.assertEqual(LogEntry.objects.filter(user=self.manager, object_id=str(job.pk)).count(), 1)
        with self.assertRaises(ValidationError):
            retry_admin_notification(job.pk, actor=self.manager)
        self.send.assert_not_called()

    def test_uncertain_retry_requires_check_and_expired_lease(self):
        job = self.uncertain(self.create())
        with self.assertRaises(ValidationError):
            retry_admin_notification(job.pk, actor=self.manager)
        job.locked_at = timezone.now()
        job.save()
        with self.assertRaises(ValidationError):
            retry_admin_notification(job.pk, actor=self.manager, confirmed_absent=True)
        job.locked_at = timezone.now() - timedelta(minutes=3)
        job.save()
        self.assertEqual(retry_admin_notification(job.pk, actor=self.manager, confirmed_absent=True).status, "PENDING")

    def test_foreign_destination_and_unauthorized_actor_cannot_retry(self):
        job = self.uncertain(self.create())
        with self.assertRaises(PermissionDenied):
            retry_admin_notification(job.pk, actor=self.user, confirmed_absent=True)
        with override_settings(TELEGRAM_STUDIO_ADMIN_CHAT_ID="12345"), self.assertRaises(ValidationError):
            retry_admin_notification(job.pk, actor=self.manager, confirmed_absent=True)

    def test_old_failed_message_cannot_follow_newer_sent_state(self):
        row = self.create()
        first = row.admin_notifications.get()
        first.status = "FAILED"
        first.save()
        row.price = 2800000
        row.save(update_fields=["price", "updated_at"])
        process_next_admin_notification()
        with self.assertRaises(ValidationError):
            retry_admin_notification(first.pk, actor=self.manager)

    def test_old_retry_cannot_overtake_newer_inflight_or_uncertain_event(self):
        row = self.create()
        first = row.admin_notifications.get()
        first.status = "FAILED"
        first.save()
        row.price = 2800000
        row.save(update_fields=["price", "updated_at"])
        newer = row.admin_notifications.exclude(pk=first.pk).get()
        for state in ("SENDING", "UNCERTAIN"):
            with self.subTest(state=state):
                newer.status = state
                newer.save()
                with self.assertRaises(ValidationError):
                    retry_admin_notification(first.pk, actor=self.manager)
        self.send.assert_not_called()

    def test_claim_rechecks_order_when_older_event_was_just_requeued(self):
        row = self.create()
        first = row.admin_notifications.get()
        first.status = "FAILED"
        first.save()
        row.price = 2800000
        row.save(update_fields=["price", "updated_at"])
        token = uuid.uuid4()
        def concurrent_recovery():
            StudioAdminNotification.objects.filter(pk=first.pk).update(status="PENDING")
            return token
        with patch("main.studio_admin_notifications.uuid.uuid4", side_effect=concurrent_recovery):
            self.assertIsNone(claim_admin_notification())
        self.assertEqual(row.admin_notifications.filter(status="PENDING").count(), 2)
        self.send.assert_not_called()

    def test_existing_private_message_can_be_reconciled_without_network(self):
        job = self.uncertain(self.create())
        with self.assertRaises(ValidationError):
            reconcile_admin_notification(job.pk, 90, actor=self.manager, verified=False)
        found = reconcile_admin_notification(job.pk, 90, actor=self.manager, verified=True)
        self.assertEqual((found.status, found.telegram_message_id), ("SENT", 90))
        self.assertEqual(LogEntry.objects.filter(user=self.manager, object_id=str(job.pk)).count(), 1)
        self.send.assert_not_called()

    def test_same_private_message_cannot_be_attached_twice(self):
        first = self.uncertain(self.create())
        reconcile_admin_notification(first.pk, 90, actor=self.manager, verified=True)
        second = self.uncertain(self.create("N-124"))
        with self.assertRaises(ValidationError):
            reconcile_admin_notification(second.pk, 90, actor=self.manager, verified=True)

    @override_settings(TELEGRAM_STUDIO_ADMIN_CHAT_ID="99999999999999999999")
    def test_oversize_admin_config_does_not_break_product_save(self):
        self.create()
        self.assertFalse(StudioAdminNotification.objects.exists())

    def test_private_queue_is_manager_only_and_validates_actions(self):
        row = self.create()
        url = reverse("studio_admin_notifications")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"notification_id": "9" * 100, "action": "retry"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"notification_id": row.admin_notifications.get().pk, "action": "retry"}).status_code, 302)
        self.assertEqual(row.admin_notifications.get().status, "PENDING")
        self.send.assert_not_called()

    @patch("main.management.commands.studio_delivery_check.get_chat")
    def test_configuration_check_default_never_calls_network(self, check):
        self.create()
        stdout = StringIO()
        call_command("studio_delivery_check", stdout=stdout)
        check.assert_not_called()
        self.send.assert_not_called()
        self.assertIn("No network call made", stdout.getvalue())

    @patch("main.management.commands.studio_delivery_check.get_chat")
    def test_network_diagnostic_only_reads_three_destinations(self, check):
        check.side_effect = [{"id": -5595039112, "type": "group"}, {"id": -5182713369, "type": "group"}, {"id": 212832276, "type": "private"}]
        self.create()
        before = list(StudioAdminNotification.objects.values())
        call_command("studio_delivery_check", network=True, stdout=StringIO())
        self.assertEqual(check.call_count, 3)
        self.assertEqual(before, list(StudioAdminNotification.objects.values()))
        self.send.assert_not_called()

    @patch("main.management.commands.studio_delivery_check.get_chat", side_effect=TelegramDeliveryError("invalid_payload"))
    def test_failed_private_check_reports_safe_hint_without_secrets(self, check):
        stdout = StringIO()
        with self.assertRaises(CommandError):
            call_command("studio_delivery_check", network=True, destination="admin", stdout=stdout)
        self.assertIn("compare deployed Worker version", stdout.getvalue())
        self.assertNotIn("test-token", stdout.getvalue())

    @patch("main.studio_transport._request")
    def test_get_chat_checks_identity_type_and_projects_safe_fields(self, request):
        request.return_value = {"id": 212832276, "type": "private", "invite_link": "private-secret"}
        self.assertEqual(get_chat(212832276), {"id": 212832276, "type": "private"})
        request.assert_called_with("getChat", {"chat_id": "212832276"})
        request.return_value = {"id": 212832276, "type": "group"}
        with self.assertRaises(TelegramDeliveryError):
            get_chat(212832276)
        request.return_value = {"id": -5595039112, "type": "private"}
        with self.assertRaises(TelegramDeliveryError):
            get_chat(-5595039112)
