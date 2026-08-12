from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .telegram_notifications import send_lead_request_notification


class TelegramRelayHotfixTests(SimpleTestCase):
    @override_settings(
        TELEGRAM_LEAD_RELAY_URL="https://relay.example/",
        TELEGRAM_LEAD_RELAY_SECRET="shared-secret",
    )
    @patch("main.telegram_notifications._send_via_relay", return_value=True)
    @patch("main.telegram_notifications.LeadRequest.objects.select_related")
    def test_configured_relay_is_used(
        self,
        select_related,
        send_via_relay,
    ):
        lead = object()
        select_related.return_value.get.return_value = lead

        result = send_lead_request_notification(42)

        self.assertTrue(result)
        select_related.assert_called_once_with("product")
        select_related.return_value.get.assert_called_once_with(pk=42)
        send_via_relay.assert_called_once_with(
            42,
            lead,
            "https://relay.example/",
            "shared-secret",
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

