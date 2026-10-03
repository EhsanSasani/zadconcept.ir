"""Exercise the combined release without contacting Telegram or production data."""
import tempfile
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from main.models import Category, Florist, Product, StudioAdminNotification, StudioDelivery, StudioProduct
from main.studio_admin_notifications import (
    claim_admin_notification, process_next_admin_notification,
    reconcile_admin_notification, retry_admin_notification,
)
from main.studio_delivery import (
    claim_delivery, process_next_delivery, product_caption, queue_retirement,
    retry_delivery, set_portal_status, soft_delete_product,
)
from main.studio_publishing import create_portal_record
from main.studio_transport import TelegramDeliveryError
from main.team_forms import TeamProductForm
from main.telegram_same_day.service import process_update
from .test_telegram_same_day import image_file


DAILY_GROUP = -5595039112
CUSTOM_GROUP = -5182713369


@override_settings(
    STUDIO_ADMIN_NOTIFICATIONS_ENABLED=False,
    TELEGRAM_STUDIO_ADMIN_CHAT_ID="212832276",
    TELEGRAM_SAME_DAY_GROUP_ID=str(DAILY_GROUP),
    TELEGRAM_STUDIO_CUSTOM_GROUP_ID=str(CUSTOM_GROUP),
    TELEGRAM_CHANNEL_ID="", TELEGRAM_DISCUSSION_GROUP_ID="",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class StudioReconciliationTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        category = Category.objects.create(name="گل", slug="reconcile", section="flowers")
        config = override_settings(MEDIA_ROOT=media.name, TELEGRAM_SAME_DAY_CATEGORY_ID=str(category.pk))
        config.enable()
        self.addCleanup(config.disable)
        self.user = get_user_model().objects.create_user("reconcile-maker")
        self.manager = get_user_model().objects.create_superuser("reconcile-manager")
        self.florist = Florist.objects.create(name="سازنده", code="reconcile", user=self.user)
        self.sequence = 0
        self.send = self._patch("main.studio_transport.send_photo", side_effect=self.message)
        self.delete = self._patch("main.studio_transport.delete_message", return_value=True)
        self.edit = self._patch("main.studio_transport.edit_caption", return_value=True)

    def _patch(self, target, **kwargs):
        mocker = patch(target, **kwargs)
        self.addCleanup(mocker.stop)
        return mocker.start()

    def message(self, chat_id, *_):
        self.sequence += 1
        return {"message_id": 9000 + self.sequence, "chat": {"id": chat_id, "type": "group"},
                "date": int(timezone.now().timestamp()), "from": {"id": 99, "is_bot": True},
                "photo": [{"file_id": "mock-photo", "width": 100, "height": 100}]}

    def create(self, production="DAILY"):
        row, _ = create_portal_record(
            user=self.user, florist=self.florist, image=image_file(),
            factor_code="R-" + uuid.uuid4().hex[:12], product_type="box",
            production_type=production, price=2500000, submission_key=uuid.uuid4(),
        )
        return row

    def publish(self, production="DAILY"):
        row = self.create(production)
        self.assertEqual(process_next_delivery().status, StudioDelivery.Status.SENT)
        row.refresh_from_db()
        return row

    def reply(self, row, status):
        original = {
            "message_id": row.telegram_message_id,
            "chat": {"id": row.telegram_chat_id, "type": "group"},
            "date": int(timezone.now().timestamp()),
            "from": {"id": 99, "is_bot": True},
            "caption": product_caption(row),
            "photo": [{"file_id": "mock-photo", "width": 100, "height": 100}],
        }
        text = "فروخته شد" if status == StudioProduct.Status.SOLD else "کشیده شد"
        return process_update("message", {
            "message_id": row.telegram_message_id + 100,
            "chat": original["chat"], "date": original["date"],
            "from": {"id": 702, "is_bot": False}, "text": text,
            "reply_to_message": original,
        }, 100000 + row.telegram_message_id)

    def test_daily_replies_hide_stock_now_and_delete_only_after_45_minutes(self):
        for production in ("DAILY",):
            for status in (StudioProduct.Status.SOLD, StudioProduct.Status.WITHDRAWN):
                with self.subTest(production=production, status=status):
                    row = self.publish(production)
                    self.reply(row, status)
                    row.refresh_from_db()
                    terminal_at = row.sold_at if status == StudioProduct.Status.SOLD else row.withdrawn_at
                    job = row.deliveries.get(action="RETIRE")
                    self.assertEqual(job.next_attempt_at, terminal_at + timedelta(minutes=45))
                    self.assertEqual(row.status, status)
                    self.assertTrue(row.image.storage.exists(row.image.name))
                    if row.product_id:
                        self.assertFalse(Product.objects.for_same_day().published().filter(pk=row.product_id).exists())
                    self.delete.reset_mock()
                    self.edit.reset_mock()
                    with patch("main.studio_delivery.timezone.now", return_value=job.next_attempt_at - timedelta(microseconds=1)):
                        self.assertIsNone(process_next_delivery())
                    self.delete.assert_not_called()
                    self.edit.assert_not_called()
                    with patch("main.studio_delivery.timezone.now", return_value=job.next_attempt_at):
                        self.assertEqual(process_next_delivery().outcome, "deleted")
                    self.delete.assert_called_once_with(row.telegram_chat_id, row.telegram_message_id)
                    self.assertIsNone(process_next_delivery())
        self.assertFalse(StudioAdminNotification.objects.exists())

    def test_administrative_delete_brings_a_waiting_retirement_forward(self):
        row = self.publish()
        row = set_portal_status(row, "SOLD", actor=self.manager)
        waiting = row.deliveries.get(action="RETIRE")
        self.assertIsNone(process_next_delivery())
        row = soft_delete_product(row, actor=self.manager, reason="ثبت اشتباه")
        waiting.refresh_from_db()
        self.assertLessEqual(waiting.next_attempt_at, timezone.now())
        self.assertLess(waiting.next_attempt_at - row.deleted_at, timedelta(seconds=1))
        self.assertEqual(process_next_delivery().outcome, "deleted")
        self.delete.assert_called_once_with(DAILY_GROUP, row.telegram_message_id)
        self.assertEqual(row.deliveries.filter(action="RETIRE").count(), 1)
        self.assertEqual(row.deleted_by, self.manager)
        self.assertTrue(row.image.storage.exists(row.image.name))

    def test_repeated_status_does_not_restart_the_45_minute_clock(self):
        row = set_portal_status(self.publish(), "SOLD", actor=self.manager)
        job = row.deliveries.get(action="RETIRE")
        deadline = job.next_attempt_at
        with patch("main.studio_delivery.timezone.now", return_value=deadline - timedelta(minutes=1)):
            set_portal_status(row, "SOLD", actor=self.manager)
        job.refresh_from_db()
        self.assertEqual(job.next_attempt_at, deadline)
        self.assertEqual(row.deliveries.filter(action="RETIRE").count(), 1)

    def test_an_old_immediate_job_is_deferred_without_a_telegram_call(self):
        row = set_portal_status(self.publish(), "SOLD", actor=self.manager)
        job = row.deliveries.get(action="RETIRE")
        deadline = job.next_attempt_at
        StudioDelivery.objects.filter(pk=job.pk).update(next_attempt_at=timezone.now())
        processed = process_next_delivery()
        self.assertEqual(processed.status, "RETRY")
        self.assertEqual(processed.next_attempt_at, deadline)
        self.assertEqual(processed.attempts, 0)
        self.delete.assert_not_called()
        self.edit.assert_not_called()

    def test_manual_retry_cannot_bypass_the_grace_period(self):
        row = set_portal_status(self.publish(), "WITHDRAWN", actor=self.manager)
        job = row.deliveries.get(action="RETIRE")
        deadline = job.next_attempt_at
        StudioDelivery.objects.filter(pk=job.pk).update(status="FAILED", last_error="telegram_forbidden")
        recovered = retry_delivery(job.pk)
        self.assertEqual(recovered.next_attempt_at, deadline)
        self.assertIsNone(process_next_delivery())
        self.delete.assert_not_called()

    def test_human_deleted_message_is_successful_and_never_republished(self):
        row = set_portal_status(self.publish(), "SOLD", actor=self.manager)
        job = row.deliveries.get(action="RETIRE")
        self.delete.side_effect = TelegramDeliveryError("message_not_found")
        with patch("main.studio_delivery.timezone.now", return_value=job.next_attempt_at):
            completed = process_next_delivery()
            self.assertEqual(completed.outcome, "already_absent")
            queue_retirement(row)
            self.assertIsNone(process_next_delivery())
        self.send.assert_called_once()
        self.edit.assert_not_called()

    def test_restart_recovers_retirement_without_a_second_photo(self):
        row = set_portal_status(self.publish(), "SOLD", actor=self.manager)
        deadline = row.deliveries.get(action="RETIRE").next_attempt_at
        with patch("main.studio_delivery.timezone.now", return_value=deadline):
            leased = claim_delivery()
            StudioDelivery.objects.filter(pk=leased.pk).update(locked_at=deadline - timedelta(minutes=5))
            self.assertEqual(process_next_delivery().outcome, "deleted")
        self.send.assert_called_once()
        self.delete.assert_called_once()

    def test_a_later_withdrawal_after_claim_gets_its_own_grace_period(self):
        row = set_portal_status(self.publish(), "SOLD", actor=self.manager)
        deadline = row.deliveries.get(action="RETIRE").next_attempt_at
        with patch("main.studio_delivery.timezone.now", return_value=deadline):
            job = claim_delivery()
            self.reply(row, StudioProduct.Status.WITHDRAWN)
            from main.studio_delivery import _retire
            _retire(job)
        job.refresh_from_db()
        self.assertEqual(job.next_attempt_at, deadline + timedelta(minutes=45))
        self.assertEqual(job.status, "RETRY")
        self.delete.assert_not_called()
        self.edit.assert_not_called()

    def test_status_replay_preserves_a_backoff_recorded_after_its_queue_snapshot(self):
        row = set_portal_status(self.publish(), "SOLD", actor=self.manager)
        job = row.deliveries.get(action="RETIRE")
        StudioDelivery.objects.filter(pk=job.pk).update(status="RETRY", last_error="")
        retry_at = job.next_attempt_at + timedelta(minutes=5)
        get_or_create = StudioDelivery.objects.get_or_create

        def worker_finishes_after_snapshot(*args, **kwargs):
            snapshot, created = get_or_create(*args, **kwargs)
            StudioDelivery.objects.filter(pk=snapshot.pk).update(
                status="RETRY", last_error="rate_limited", next_attempt_at=retry_at,
            )
            return snapshot, created

        with patch.object(StudioDelivery.objects, "get_or_create", side_effect=worker_finishes_after_snapshot):
            queue_retirement(row)
        job.refresh_from_db()
        self.assertEqual(job.next_attempt_at, retry_at)
        self.assertEqual(job.last_error, "rate_limited")
        with patch("main.studio_delivery.timezone.now", return_value=retry_at - timedelta(seconds=1)):
            self.assertIsNone(process_next_delivery())
        self.delete.assert_not_called()

    def test_rate_limit_survives_status_replay_and_manual_retry(self):
        row = set_portal_status(self.publish(), "SOLD", actor=self.manager)
        deadline = row.deliveries.get(action="RETIRE").next_attempt_at
        self.delete.side_effect = TelegramDeliveryError("rate_limited", retryable=True, retry_after=75)
        with patch("main.studio_delivery.timezone.now", return_value=deadline):
            job = process_next_delivery()
            retry_at = job.next_attempt_at
            self.assertEqual(retry_at, deadline + timedelta(seconds=75))
            set_portal_status(row, "SOLD", actor=self.manager)
            self.assertEqual(retry_delivery(job.pk).next_attempt_at, retry_at)
            self.assertIsNone(process_next_delivery())
        self.delete.assert_called_once()

    def test_disabled_private_queue_preserves_old_rows_and_group_worker_still_sends(self):
        row = self.create()
        for status in ("PENDING", "RETRY", "FAILED", "SENDING", "UNCERTAIN"):
            StudioAdminNotification.objects.create(
                record=row, event="CREATED", chat_id=212832276, caption="اعلان قبلی",
                status=status, attempts=1, last_error="invalid_payload",
                locked_at=timezone.now() - timedelta(minutes=10),
            )
        before = list(StudioAdminNotification.objects.values())
        self.assertIsNone(claim_admin_notification())
        self.assertIsNone(process_next_admin_notification())
        output = StringIO()
        with patch("main.management.commands.process_studio_deliveries.process_next_admin_notification") as private:
            call_command("process_studio_deliveries", once=True, stdout=output)
        private.assert_not_called()
        self.send.assert_called_once()
        self.assertEqual(self.send.call_args.args[0], DAILY_GROUP)
        self.assertNotIn("admin_notification=", output.getvalue())
        self.assertEqual(list(StudioAdminNotification.objects.values()), before)

    def test_create_price_sale_and_delete_never_queue_private_notifications(self):
        row = self.publish("CUSTOM")
        row.price = 2700000
        row.save(update_fields=["price", "updated_at"])
        row = set_portal_status(row, "SOLD", actor=self.manager)
        soft_delete_product(row, actor=self.manager, reason="ثبت اشتباه")
        self.assertFalse(StudioAdminNotification.objects.exists())

    def test_disabled_private_recovery_cannot_resume_abandoned_jobs(self):
        row = self.create("CUSTOM")
        job = StudioAdminNotification.objects.create(
            record=row, event="CREATED", chat_id=212832276, caption="اعلان قبلی", status="FAILED",
        )
        before = StudioAdminNotification.objects.values().get(pk=job.pk)
        with self.assertRaises(ValidationError):
            retry_admin_notification(job.pk, actor=self.manager)
        with self.assertRaises(ValidationError):
            reconcile_admin_notification(job.pk, 99, actor=self.manager, verified=True)
        self.assertEqual(StudioAdminNotification.objects.values().get(pk=job.pk), before)
        self.send.assert_not_called()

    def test_disabled_private_history_is_read_only_and_hidden_from_group_actions(self):
        row = self.create("CUSTOM")
        job = StudioAdminNotification.objects.create(
            record=row, event="CREATED", chat_id=212832276, caption="اعلان قبلی", status="FAILED",
        )
        self.client.force_login(self.manager)
        history_url = reverse("studio_admin_notifications")
        groups = self.client.get(reverse("studio_deliveries"))
        self.assertNotContains(groups, history_url)
        history = self.client.get(history_url)
        self.assertContains(history, "اعلان خصوصی مدیر غیرفعال است")
        self.assertNotContains(history, 'name="notification_id"')
        response = self.client.post(history_url, {"notification_id": job.pk, "action": "retry"})
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")

    def test_diagnostics_do_not_probe_a_disabled_private_destination(self):
        output = StringIO()
        with patch("main.management.commands.studio_delivery_check.get_chat") as get_chat:
            call_command("studio_delivery_check", network=True, destination="admin", stdout=output)
        get_chat.assert_not_called()
        self.assertIn("admin=disabled", output.getvalue())

    def test_blank_form_has_no_preselected_destination_and_rejects_missing_choice(self):
        form = TeamProductForm()
        self.assertIsNone(form.fields["production_type"].initial)
        self.client.force_login(self.user)
        response = self.client.get(reverse("team_product_add"))
        self.assertNotContains(response, ' checked')
        self.assertContains(response, 'value="DAILY" required')
        self.assertContains(response, 'value="CUSTOM" required')
        rejected = self.client.post(reverse("team_product_add"), {
            "image": image_file(), "florist": self.florist.pk, "price": "2,500,000",
            "product_type": "box", "factor_code": "R-MISSING", "submission_key": uuid.uuid4(),
        }, HTTP_ACCEPT="application/json")
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("production_type", rejected.json()["errors"])
        self.assertFalse(StudioProduct.objects.exists())
        self.assertFalse(StudioDelivery.objects.exists())

    def test_comma_and_persian_prices_are_stored_as_the_correct_amount(self):
        self.client.force_login(self.user)
        for amount in ("2,500,000", "۲٬۵۰۰٬۰۰۰", "٢,٥٠٠,٠٠٠"):
            with self.subTest(amount=amount):
                response = self.client.post(reverse("team_product_add"), {
                    "image": image_file(), "florist": self.florist.pk, "price": amount,
                    "production_type": "CUSTOM", "product_type": "box",
                    "factor_code": "R-" + uuid.uuid4().hex[:12], "submission_key": uuid.uuid4(),
                }, HTTP_ACCEPT="application/json")
                self.assertEqual(response.status_code, 201)
                row = StudioProduct.objects.get(pk=response.json()["record_id"])
                self.assertEqual(row.price, 2500000)
                self.assertEqual(row.deliveries.get().chat_id, CUSTOM_GROUP)
        self.send.assert_not_called()
