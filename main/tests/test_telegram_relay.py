import json
from io import StringIO
from unittest.mock import patch

from django.test import TestCase, override_settings

from ..models import TelegramBotUser
from ..telegram_notifications import (
    TELEGRAM_RELAY_USER_AGENT,
    _send_via_relay,
    send_lead_request_notification,
)


class TelegramRelayTests(TestCase):
    @override_settings(
        TELEGRAM_LEAD_RELAY_URL="https://relay.example/",
        TELEGRAM_LEAD_RELAY_SECRET="shared-secret",
    )
    @patch("main.telegram_notifications._send_via_relay", return_value=True)
    @patch("main.telegram_notifications.LeadRequest.objects.select_related")
    def test_configured_relay_without_recipients_fails_safely(
        self,
        select_related,
        send_via_relay,
    ):
        lead = object()
        select_related.return_value.get.return_value = lead

        result = send_lead_request_notification(42)

        self.assertFalse(result)
        select_related.assert_called_once_with("product")
        select_related.return_value.get.assert_called_once_with(pk=42)
        send_via_relay.assert_not_called()

    @override_settings(
        TELEGRAM_LEAD_RELAY_URL="https://relay.example/",
        TELEGRAM_LEAD_RELAY_SECRET="shared-secret",
    )
    @patch("main.telegram_notifications._send_via_relay", return_value=True)
    @patch("main.telegram_notifications.LeadRequest.objects.select_related")
    def test_configured_relay_sends_to_active_lead_recipients(
        self,
        select_related,
        send_via_relay,
    ):
        TelegramBotUser.objects.create(
            name="Second seller",
            telegram_user_id=202,
            can_receive_leads=True,
        )
        TelegramBotUser.objects.create(
            name="First seller",
            telegram_user_id=101,
            can_receive_leads=True,
        )
        TelegramBotUser.objects.create(
            name="Lookup only",
            telegram_user_id=303,
            can_lookup_products=True,
        )
        TelegramBotUser.objects.create(
            name="Inactive seller",
            telegram_user_id=404,
            can_receive_leads=True,
            is_active=False,
        )
        lead = object()
        select_related.return_value.get.return_value = lead

        result = send_lead_request_notification(42)

        self.assertTrue(result)
        send_via_relay.assert_called_once_with(
            42,
            lead,
            "https://relay.example/",
            "shared-secret",
            chat_ids=[101, 202],
        )

    @override_settings(
        TELEGRAM_LEAD_RELAY_URL="https://relay.example/",
        TELEGRAM_LEAD_RELAY_SECRET="",
    )
    @patch("main.telegram_notifications.LeadRequest.objects.select_related")
    def test_incomplete_relay_configuration_fails_without_database_lookup(
        self,
        select_related,
    ):
        result = send_lead_request_notification(42)

        self.assertFalse(result)
        select_related.assert_not_called()

    @override_settings(TELEGRAM_LEAD_TIMEOUT_SECONDS=5)
    @patch(
        "main.telegram_notifications.format_lead_request_message",
        return_value="test message",
    )
    @patch("main.telegram_notifications.urlopen")
    def test_relay_request_uses_cloudflare_compatible_user_agent(
        self,
        urlopen,
        format_message,
    ):
        lead = object()
        urlopen.return_value = StringIO('{"ok": true}')

        result = _send_via_relay(
            42,
            lead,
            "https://relay.example/",
            "shared-secret",
            chat_ids=[101, 202],
        )

        self.assertTrue(result)
        format_message.assert_called_once_with(lead)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["chat_ids"], ["101", "202"])
        self.assertEqual(
            request.get_header("User-agent"),
            TELEGRAM_RELAY_USER_AGENT,
        )
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 5)
