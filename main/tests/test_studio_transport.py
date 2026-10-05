import base64
import json
from io import BytesIO
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.test import SimpleTestCase, override_settings

from main import studio_transport as transport


JPEG = b"\xff\xd8\xff\xe0sample-photo\xff\xd9"
GROUP = "-10077777"
MESSAGE = {"message_id": 42, "chat": {"id": int(GROUP), "type": "supergroup"}}


class Response(BytesIO):
    status = 200

    def __init__(self, payload, status=200):
        super().__init__(json.dumps(payload).encode() if not isinstance(payload, bytes) else payload)
        self.status = status


@override_settings(
    TELEGRAM_SAME_DAY_GROUP_ID=GROUP,
    TELEGRAM_STUDIO_CUSTOM_GROUP_ID="",
    TELEGRAM_STUDIO_ADMIN_CHAT_ID="",
    TELEGRAM_BOT_TOKEN="private-token",
    TELEGRAM_SAME_DAY_RELAY_URL="",
    TELEGRAM_LEAD_RELAY_SECRET="private-secret",
    STUDIO_TELEGRAM_TIMEOUT_SECONDS=35,
)
class StudioTransportTests(SimpleTestCase):
    def setUp(self):
        self.opener = self.enterContext(patch("main.studio_transport.build_opener")).return_value
        self.opener.open.return_value = Response({"ok": True, "result": MESSAGE})

    def api_error(self, status, description, **extra):
        self.opener.open.side_effect = HTTPError(
            "https://api.telegram.org/botprivate-token/sendPhoto", status,
            "private-token", {}, BytesIO(json.dumps({
                "ok": False, "error_code": status, "description": description, **extra,
            }).encode()),
        )

    @override_settings(TELEGRAM_STUDIO_CUSTOM_GROUP_ID="-5182713369")
    def test_custom_destination_is_allowed_in_direct_and_relay_transport(self):
        message = {**MESSAGE, "chat": {"id": -5182713369, "type": "group"}}
        for relay in ("", "https://relay.example/"):
            with self.subTest(relay=relay), override_settings(TELEGRAM_SAME_DAY_RELAY_URL=relay):
                self.opener.open.return_value = Response({"ok": True, "result": message})
                self.assertEqual(transport.send_photo(-5182713369, JPEG, "قیمت\nفاکتور"), message)
                request = self.opener.open.call_args.args[0]
                if relay:
                    self.assertEqual(json.loads(request.data)["chat_id"], "-5182713369")
                else:
                    self.assertIn(b"-5182713369", request.data)

    def test_direct_photo_uses_multipart_bytes_and_plain_caption(self):
        result = transport.send_photo(int(GROUP), JPEG, "قیمت: ۲۵۰٬۰۰۰ تومان\nفاکتور: A23")
        self.assertEqual(result, MESSAGE)
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.telegram.org/botprivate-token/sendPhoto")
        self.assertEqual(request.method, "POST")
        self.assertIn("multipart/form-data; boundary=", request.get_header("Content-type"))
        self.assertIn(JPEG, request.data)
        self.assertIn('name="caption"'.encode(), request.data)
        self.assertNotIn(b"parse_mode", request.data)
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 35)

    @override_settings(TELEGRAM_SAME_DAY_RELAY_URL="https://relay.example/")
    def test_relay_uses_fixed_route_existing_secret_and_base64(self):
        self.assertEqual(transport.send_photo(GROUP, JPEG, "قیمت\nفاکتور"), MESSAGE)
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://relay.example/studio-delivery")
        self.assertEqual(request.get_header("Authorization"), "Bearer private-secret")
        payload = json.loads(request.data)
        self.assertEqual(payload, {"method": "sendPhoto", "chat_id": GROUP,
                                  "caption": "قیمت\nفاکتور", "photo_base64": base64.b64encode(JPEG).decode()})
        self.assertNotIn("private-token", request.data.decode())

    def test_invalid_destination_photo_caption_or_message_id_never_reaches_network(self):
        calls = [
            lambda: transport.send_photo("-999", JPEG, "price"),
            lambda: transport.send_photo(GROUP, b"not a JPEG", "price"),
            lambda: transport.send_photo(GROUP, JPEG, ""),
            lambda: transport.send_photo(GROUP, JPEG, "a" * 1025),
            lambda: transport.send_photo(GROUP, JPEG, "🌹" * 513),
            lambda: transport.send_photo(GROUP, JPEG, "\ud800"),
            lambda: transport.delete_message(GROUP, True),
            lambda: transport.delete_message(GROUP, 0),
            lambda: transport.delete_message(GROUP, "42"),
        ]
        for call in calls:
            with self.subTest(call=call), self.assertRaises(transport.TelegramDeliveryError) as error:
                call()
            self.assertEqual(error.exception.code, "invalid_payload")
            self.assertFalse(error.exception.retryable)
        self.opener.open.assert_not_called()

    def test_photo_size_limit_prevents_network_request(self):
        with patch.object(transport, "MAX_PHOTO_BYTES", len(JPEG) - 1):
            with self.assertRaises(transport.TelegramDeliveryError) as error:
                transport.send_photo(GROUP, JPEG, "price")
        self.assertEqual(error.exception.code, "invalid_payload")
        self.opener.open.assert_not_called()

    def test_other_configured_destinations_cannot_authorize_an_unconfigured_ready_group(self):
        # A configured custom/private destination is not the same as having
        # no destinations. Both must still reject the absent ready group.
        for custom, admin in (("-5182713369", ""), ("", "212832276")):
            with self.subTest(custom=custom, admin=admin), override_settings(
                TELEGRAM_SAME_DAY_GROUP_ID="",
                TELEGRAM_STUDIO_CUSTOM_GROUP_ID=custom,
                TELEGRAM_STUDIO_ADMIN_CHAT_ID=admin,
            ):
                with self.assertRaises(transport.TelegramDeliveryError) as error:
                    transport.send_photo(GROUP, JPEG, "price")
                self.assertEqual(error.exception.code, "invalid_payload")
                self.assertFalse(error.exception.retryable)
        self.opener.open.assert_not_called()

    def test_missing_group_or_unsafe_relay_configuration_never_reaches_network(self):
        settings_cases = [
            {"TELEGRAM_SAME_DAY_GROUP_ID": ""},
            {"TELEGRAM_BOT_TOKEN": ""},
            {"TELEGRAM_BOT_TOKEN": "secret/evil?redirect=1"},
            {"TELEGRAM_SAME_DAY_RELAY_URL": "http://relay.example"},
            {"TELEGRAM_SAME_DAY_RELAY_URL": "https://[malformed"},
            {"TELEGRAM_SAME_DAY_RELAY_URL": "https://user:secret@relay.example"},
            {"TELEGRAM_SAME_DAY_RELAY_URL": "https://relay.example?token=secret"},
            {"TELEGRAM_SAME_DAY_RELAY_URL": "https://relay.example", "TELEGRAM_LEAD_RELAY_SECRET": ""},
        ]
        for case in settings_cases:
            with self.subTest(case=case), override_settings(**case):
                with self.assertRaises(transport.TelegramDeliveryError) as error:
                    transport.send_photo(GROUP, JPEG, "price")
                self.assertEqual(error.exception.code, "configuration_error")
        self.opener.open.assert_not_called()

    def test_rate_limit_is_definite_retry_with_server_delay(self):
        self.api_error(429, "secret-token", parameters={"retry_after": 123})
        with self.assertRaises(transport.TelegramDeliveryError) as error:
            transport.send_photo(GROUP, JPEG, "price")
        self.assertEqual(error.exception.code, "rate_limited")
        self.assertTrue(error.exception.retryable)
        self.assertFalse(error.exception.uncertain)
        self.assertEqual(error.exception.retry_after, 123)
        self.assertNotIn("secret", str(error.exception))

    def test_confirmed_telegram_server_rejection_retries(self):
        self.api_error(500, "Internal server error")
        with self.assertRaises(transport.TelegramDeliveryError) as error:
            transport.send_photo(GROUP, JPEG, "price")
        self.assertEqual(error.exception.code, "telegram_server_error")
        self.assertTrue(error.exception.retryable)

    def test_network_send_error_is_uncertain_and_redacts_credentials(self):
        self.opener.open.side_effect = URLError("https://api.telegram.org/botprivate-token/sendPhoto private-secret")
        with self.assertRaises(transport.TelegramDeliveryError) as error:
            transport.send_photo(GROUP, JPEG, "price")
        self.assertEqual(str(error.exception), "transport_uncertain")
        self.assertTrue(error.exception.uncertain)
        self.assertFalse(error.exception.retryable)
        self.assertTrue(error.exception.__suppress_context__)

    def test_idempotent_retirement_network_failure_can_retry(self):
        self.opener.open.side_effect = TimeoutError("private-token")
        with self.assertRaises(transport.TelegramDeliveryError) as error:
            transport.delete_message(GROUP, 42)
        self.assertEqual(error.exception.code, "transport_unavailable")
        self.assertTrue(error.exception.retryable)
        self.assertFalse(error.exception.uncertain)

    def test_interrupted_http_error_body_is_safe_and_uncertain(self):
        response = HTTPError("https://api.telegram.org/botprivate-token/sendPhoto", 502, "private-token", {}, BytesIO())
        response.read = lambda *_args: (_ for _ in ()).throw(IncompleteRead(b"private-token"))
        self.opener.open.side_effect = response
        with self.assertRaises(transport.TelegramDeliveryError) as error:
            transport.send_photo(GROUP, JPEG, "price")
        self.assertEqual(str(error.exception), "transport_uncertain")
        self.assertTrue(error.exception.uncertain)
        self.assertTrue(error.exception.__suppress_context__)

    def test_unreadable_oversized_or_mismatched_send_responses_are_uncertain(self):
        responses = [b"not json: private-token", b"x" * (transport.MAX_RESPONSE_BYTES + 1),
                     {"ok": False}, {"ok": False, "error_code": "500"},
                     {"ok": False, "error_code": True}, {"ok": False, "error_code": 200},
                     {"ok": True, "result": True}, {"ok": True, "result": {**MESSAGE, "chat": {"id": -999}}},
                     {"ok": True, "result": {"message_id": True, "chat": MESSAGE["chat"]}}, []]
        for response in responses:
            with self.subTest(response=str(response)[:60]):
                self.opener.open.return_value = Response(response)
                with self.assertRaises(transport.TelegramDeliveryError) as error:
                    transport.send_photo(GROUP, JPEG, "price")
                self.assertTrue(error.exception.uncertain)
                self.assertFalse(error.exception.retryable)

    def test_missing_delete_and_unchanged_caption_are_successful_replays(self):
        self.api_error(400, "Bad Request: message to delete not found")
        self.assertTrue(transport.delete_message(GROUP, 42))
        self.api_error(400, "Bad Request: message is not modified")
        self.assertTrue(transport.edit_caption(GROUP, 42, "فروخته شد"))

    def test_undeletable_message_is_safe_permanent_error_for_caption_fallback(self):
        self.api_error(400, "Bad Request: message can't be deleted")
        with self.assertRaises(transport.TelegramDeliveryError) as error:
            transport.delete_message(GROUP, 42)
        self.assertEqual(error.exception.code, "message_cannot_be_deleted")
        self.assertFalse(error.exception.retryable)

    @override_settings(TELEGRAM_SAME_DAY_RELAY_URL="https://relay.example/")
    def test_relay_non_2xx_preserves_safe_uncertainty_envelope(self):
        self.opener.open.side_effect = HTTPError("https://relay.example", 503, "private-secret", {}, BytesIO(json.dumps({
            "ok": False, "error": "transport_uncertain", "retryable": False, "uncertain": True,
        }).encode()))
        with self.assertRaises(transport.TelegramDeliveryError) as error:
            transport.send_photo(GROUP, JPEG, "price")
        self.assertEqual(error.exception.code, "transport_uncertain")
        self.assertTrue(error.exception.uncertain)

    @override_settings(TELEGRAM_SAME_DAY_RELAY_URL="https://relay.example/")
    def test_legacy_or_untrusted_relay_error_cannot_leak_diagnostics(self):
        for payload in [
            {"ok": False, "error": "https://secret@relay.example/private-token", "retryable": True, "uncertain": False},
            {"ok": False, "error": "Unauthorized"},
            {"ok": False, "error": {"private-token": "bad"}, "retryable": True, "uncertain": False},
        ]:
            self.opener.open.return_value = Response(payload, status=502)
            with self.assertRaises(transport.TelegramDeliveryError) as error:
                transport.send_photo(GROUP, JPEG, "price")
            self.assertEqual(str(error.exception), "invalid_response")
            self.assertTrue(error.exception.uncertain)

    def test_non_json_http_429_still_honors_retry_after(self):
        self.opener.open.side_effect = HTTPError("https://api.telegram.org/botprivate-token/sendPhoto", 429,
                                                "private-token", {"Retry-After": "17"}, BytesIO(b"throttled"))
        with self.assertRaises(transport.TelegramDeliveryError) as error:
            transport.send_photo(GROUP, JPEG, "price")
        self.assertEqual(error.exception.retry_after, 17)
        self.assertTrue(error.exception.retryable)

    def test_sales_media_edit_is_multipart_with_same_message_identity(self):
        transport.edit_photo(GROUP, 42, JPEG, 'updated price')
        request = self.opener.open.call_args.args[0]
        self.assertTrue(request.full_url.endswith('/editMessageMedia'))
        self.assertIn(b'attach://photo', request.data)
        self.assertIn(b'name="message_id"\r\n\r\n42', request.data)
        self.assertIn(JPEG, request.data)
        self.assertNotIn(b'parse_mode', request.data)

    @override_settings(TELEGRAM_SAME_DAY_RELAY_URL='https://relay.example/')
    def test_sales_media_edit_relay_has_exact_envelope(self):
        transport.edit_photo(GROUP, 42, JPEG, 'updated price')
        payload = json.loads(self.opener.open.call_args.args[0].data)
        self.assertEqual(payload, {'method':'editMessageMedia','chat_id':GROUP,'message_id':42,
            'caption':'updated price','photo_base64':base64.b64encode(JPEG).decode()})

    def test_sales_media_edit_lost_response_retries_idempotently(self):
        self.opener.open.side_effect = URLError('private diagnostic')
        with self.assertRaises(transport.TelegramDeliveryError) as raised:
            transport.edit_photo(GROUP, 42, JPEG, 'updated price')
        self.assertTrue(raised.exception.retryable)
        self.assertFalse(raised.exception.uncertain)
