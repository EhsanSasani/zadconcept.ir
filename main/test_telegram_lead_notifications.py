import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import LeadRequest
from .telegram_notifications import (
    format_lead_request_message,
    send_lead_request_notification,
)


class TelegramLeadNotificationTests(TestCase):
    def create_lead(self, **overrides):
        values = {
            "full_name": "سارا <script>",
            "mobile": "09121234567",
            "lead_type": LeadRequest.LeadType.FLOWER,
            "delivery_window": LeadRequest.DeliveryWindow.TODAY,
            "event_location": "مشهد",
            "note": "گل <b>سفید</b>",
            "source_page": "/contact/",
        }
        values.update(overrides)
        return LeadRequest.objects.create(**values)

    def test_message_contains_all_lead_fields_and_escapes_user_input(self):
        lead = self.create_lead()

        message = format_lead_request_message(lead)

        self.assertIn("سارا &lt;script&gt;", message)
        self.assertIn("09121234567", message)
        self.assertIn("گل &lt;b&gt;سفید&lt;/b&gt;", message)
        self.assertIn("/contact/", message)
        self.assertIn(f"<code>{lead.pk}</code>", message)

    @override_settings(
        TELEGRAM_LEAD_BOT_TOKEN="test-token",
        TELEGRAM_LEAD_CHAT_ID="6675854773",
        TELEGRAM_LEAD_TIMEOUT_SECONDS=2,
    )
    @patch("main.telegram_notifications.urlopen")
    def test_sender_posts_to_configured_chat(self, mocked_urlopen):
        lead = self.create_lead()
        response = MagicMock()
        response.read.return_value = b'{"ok": true}'
        mocked_urlopen.return_value.__enter__.return_value = response

        self.assertTrue(send_lead_request_notification(lead.pk))

        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["chat_id"], "6675854773")
        self.assertEqual(payload["parse_mode"], "HTML")

    @override_settings(
        TELEGRAM_LEAD_BOT_TOKEN="test-token",
        TELEGRAM_LEAD_CHAT_ID="6675854773",
        TELEGRAM_LEAD_TIMEOUT_SECONDS=2,
    )
    @patch("main.telegram_notifications.urlopen", side_effect=URLError("offline"))
    def test_telegram_failure_does_not_delete_the_saved_lead(self, mocked_urlopen):
        lead = self.create_lead()

        self.assertFalse(send_lead_request_notification(lead.pk))
        self.assertTrue(LeadRequest.objects.filter(pk=lead.pk).exists())

    @override_settings(
        TELEGRAM_LEAD_BOT_TOKEN="test-token",
        TELEGRAM_LEAD_CHAT_ID="6675854773",
    )
    @patch("main.views.send_lead_request_notification")
    def test_valid_form_schedules_notification_after_commit(self, mocked_sender):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("lead_request"),
                {
                    "full_name": "Telegram Lead",
                    "mobile": "09121234567",
                    "lead_type": LeadRequest.LeadType.FLOWER,
                    "delivery_window": LeadRequest.DeliveryWindow.TODAY,
                    "note": "Test",
                    "next": reverse("contact"),
                    "source_page": "/contact/",
                },
            )

        self.assertEqual(response.status_code, 302)
        lead = LeadRequest.objects.get(full_name="Telegram Lead")
        mocked_sender.assert_called_once_with(lead.pk)

    def test_invalid_lead_has_no_write_callback_or_external_redirect(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            response = self.client.post(
                reverse("lead_request"),
                {
                    "full_name": "Invalid Telegram Lead",
                    "mobile": "123",
                    "lead_type": LeadRequest.LeadType.FLOWER,
                    "delivery_window": LeadRequest.DeliveryWindow.TODAY,
                    "next": "https://external.invalid/redirect-target",
                    "source_page": "/contact/",
                },
                HTTP_X_REAL_IP="203.0.113.99",
            )

        self.assertRedirects(
            response,
            reverse("index"),
            fetch_redirect_response=False,
        )
        self.assertFalse(LeadRequest.objects.exists())
        self.assertEqual(callbacks, [])
