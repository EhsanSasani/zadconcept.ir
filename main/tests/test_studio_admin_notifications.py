import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from main.models import Florist, StudioAdminNotification, StudioProduct
from main.studio_admin_notifications import process_next_admin_notification
from .test_telegram_same_day import image_file


@override_settings(
    STUDIO_ADMIN_NOTIFICATIONS_ENABLED=True,
    TELEGRAM_STUDIO_ADMIN_CHAT_ID="212832276",
    TELEGRAM_SAME_DAY_GROUP_ID="-10077777",
    TELEGRAM_STUDIO_CUSTOM_GROUP_ID="-10087654",
    TELEGRAM_SAME_DAY_RELAY_URL="",
    TELEGRAM_BOT_TOKEN="test-token",
)
class StudioAdminNotificationTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_user("maker")
        self.florist = Florist.objects.create(name="مهدی", code="mz")

    def create_record(self):
        return StudioProduct.objects.create(
            florist=self.florist,
            created_by=self.user,
            factor_code="A-123",
            product_type=StudioProduct.ProductType.BOX,
            production_type=StudioProduct.ProductionType.CUSTOM,
            price=2500000,
            image=image_file(),
            source=StudioProduct.Source.PORTAL,
        )

    def test_create_price_status_and_delete_queue_customer_safe_snapshots(self):
        record = self.create_record()
        jobs = list(StudioAdminNotification.objects.all())
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].event, StudioAdminNotification.Event.CREATED)
        self.assertEqual(
            jobs[0].caption,
            "کد: A-123\nقیمت: 2,500,000 تومان\nوضعیت: موجود",
        )
        self.assertNotIn("مهدی", jobs[0].caption)

        record.price = 2800000
        record.save(update_fields=["price", "updated_at"])
        self.assertEqual(
            StudioAdminNotification.objects.order_by("-pk").first().event,
            StudioAdminNotification.Event.PRICE,
        )

        record.status = StudioProduct.Status.SOLD
        record.sold_at = record.updated_at
        record.save(update_fields=["status", "sold_at", "updated_at"])
        self.assertEqual(
            StudioAdminNotification.objects.order_by("-pk").first().event,
            StudioAdminNotification.Event.STATUS,
        )

        record.status = StudioProduct.Status.DELETED
        record.save(update_fields=["status", "updated_at"])
        self.assertEqual(
            StudioAdminNotification.objects.order_by("-pk").first().event,
            StudioAdminNotification.Event.DELETED,
        )

    @patch("main.studio_admin_notifications.studio_transport.send_photo")
    def test_worker_sends_photo_to_configured_private_chat(self, send_photo):
        record = self.create_record()
        send_photo.return_value = {"message_id": 77, "chat": {"id": 212832276}}
        job = process_next_admin_notification()
        self.assertEqual(job.status, StudioAdminNotification.Status.SENT)
        self.assertEqual(job.telegram_message_id, 77)
        self.assertEqual(send_photo.call_args.args[0], 212832276)
        self.assertTrue(send_photo.call_args.args[1].startswith(b"\xff\xd8\xff"))
        self.assertEqual(send_photo.call_args.args[2], StudioAdminNotification.objects.get(pk=job.pk).caption)

    @override_settings(TELEGRAM_STUDIO_ADMIN_CHAT_ID="")
    def test_missing_private_chat_never_blocks_record_creation(self):
        self.create_record()
        self.assertFalse(StudioAdminNotification.objects.exists())
