import copy

from django.test import SimpleTestCase, TestCase, override_settings

from main.models import Product, TelegramSameDayPost
from main.telegram_same_day.price import PriceError, parse_group_price
from . import test_telegram_same_day as fixtures
from .test_telegram_same_day import channel_post, sold_comment, GROUP


def photo(caption="2300", *, update_id=10, edited=False):
    source = channel_post(caption, update_id=update_id, edited=edited)
    message = source.pop("edited_channel_post" if edited else "channel_post")
    message["chat"] = {"id": GROUP, "type": "supergroup"}
    message["from"] = {"id": 123, "is_bot": False}
    source["edited_message" if edited else "message"] = message
    return source


class GroupPriceTests(SimpleTestCase):
    def test_formats_and_units(self):
        cases = {"2300": 2300000, "۲۳۰۰": 2300000, "2/680 t": 2680000,
                 "۲٬۶۸۰ ت": 2680000, "2,680,000": 2680000,
                 "۲/۶۸۰/۰۰۰": 2680000, "2.68 میلیون تومان": 2680000,
                 "۲٫۶۸ میلیون": 2680000, "2.68": 2680000,
                 "قیمت: ۲۶۸۰ هزار تومان": 2680000, "2680k": 2680000,
                 "2.68m": 2680000, "2300 تومان": 2300,
                 "قیمت ۲۶۸۰۰۰۰ تومن": 2680000, "2 680 000 تومان": 2680000,
                 "دسته گل\nقیمت: ۲/۶۸۰ t": 2680000,
                 "دسته گل قیمت: ۲۳۰۰": 2300000, "💰 ۲۳۰۰": 2300000,
                 "۲/۶۸": 2680000, "۲/۵ میلیون": 2500000}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_group_price(text), expected)

    def test_uncertain_prices_fail(self):
        for text in ("قیمت توافقی", "2300\n2400", "قیمت 2,68,000", "-2300",
                     "قیمت 2300 یا 2500", "قیمت 200 ریال", "0", "گل زیبا", "09123456789", None):
            with self.subTest(text=text), self.assertRaises(PriceError):
                parse_group_price(text)


# Reuse fixtures/helpers only; do not run channel cases with group-only settings.
@override_settings(TELEGRAM_CHANNEL_ID="", TELEGRAM_DISCUSSION_GROUP_ID="",
                   TELEGRAM_SAME_DAY_GROUP_ID=str(GROUP), TELEGRAM_WEBHOOK_SECRET="test-secret")
class GroupWorkflowTests(TestCase):
    setUp = fixtures.SameDayWebhookTests.setUp
    send = fixtures.SameDayWebhookTests.send
    product = fixtures.SameDayWebhookTests.product

    def reply(self, text, *, target=None, update_id=20):
        return sold_comment(text=text, reply=target or photo()["message"], update_id=update_id)

    def test_photo_caption_duplicate_and_edit(self):
        self.assertEqual(self.send(photo()).json()["result"], "created")
        self.assertEqual(self.product().price, 2300000)
        self.send(photo())
        self.send(photo("2/680 t", edited=True, update_id=11))
        self.assertEqual(self.product().price, 2680000)
        self.assertEqual(Product.objects.count(), 1)
        self.download.assert_called_once()

    def test_photo_waits_then_price_reply_publishes_and_edits(self):
        self.send(photo("گل زیبا"))
        self.assertFalse(Product.objects.exists())
        self.download.assert_not_called()
        reply = self.reply("۲/۶۸۰ t")
        self.assertEqual(self.send(reply).json()["result"], "created")
        self.send(reply)
        edited = copy.deepcopy(reply)
        edited["edited_message"] = edited.pop("message")
        edited["edited_message"]["edit_date"] = 1700000003
        edited["edited_message"]["text"] = "۳۰۰۰"
        edited["update_id"] = 21
        self.send(edited)
        self.send(reply)
        self.assertEqual(self.product().price, 3000000)
        self.download.assert_called_once()

    def test_reply_arrives_before_original(self):
        self.send(self.reply("2/680 t"))
        self.send(photo())
        self.assertEqual(self.product().price, 2680000)
        self.download.assert_called_once()

    def test_withdrawn_hides_but_preserves_record_and_never_reopens(self):
        self.send(photo())
        product = self.product()
        self.assertEqual(self.send(self.reply("کشیده شد")).json()["result"], "withdrawn")
        self.send(self.reply("فروخته شد", update_id=22))
        self.send(self.reply("3000", update_id=23))
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.WITHDRAWN)
        self.assertFalse(Product.objects.for_same_day().published().exists())
        self.assertFalse(Product.objects.publicly_indexable().filter(pk=product.pk).exists())
        self.assertEqual(Product.objects.count(), 1)

    def test_withdrawn_before_price_and_original_is_terminal(self):
        self.send(self.reply("کشیده شد"))
        self.send(photo())
        self.assertEqual(self.product().status, Product.Status.WITHDRAWN)
        self.assertFalse(Product.objects.for_same_day().published().exists())

    def test_reply_to_price_message_can_sell(self):
        self.send(photo(""))
        price = self.reply("2300")
        self.send(price)
        parent = copy.deepcopy(price["message"])
        parent.pop("reply_to_message")
        self.send(sold_comment(reply=parent, update_id=22, message_id=502))
        self.assertEqual(self.product().status, Product.Status.SOLD)

    def test_unknown_reply_and_untrusted_photo_never_publish(self):
        target = {"message_id": 999, "chat": {"id": GROUP, "type": "supergroup"}}
        self.assertEqual(self.send(self.reply("2300", target=target)).json()["result"], "unknown_reply_ignored")
        for mutation in ({"from": {"id": 999}}, {"sender_chat": {"id": GROUP}},
                         {"forward_origin": {"type": "user"}}):
            update = photo()
            update["message"].update(mutation)
            self.assertEqual(self.send(update).status_code, 403)
            self.send(self.reply("2300", target=update["message"]))
        self.assertFalse(Product.objects.exists())
        self.download.assert_not_called()

    def test_invalid_price_reply_hides_and_retry_does_not_download(self):
        self.send(photo())
        self.send(self.reply("قیمت توافقی"))
        self.assertFalse(Product.objects.for_same_day().published().exists())
        self.send(self.reply("3000", update_id=21))
        self.assertTrue(Product.objects.for_same_day().published().exists())
        self.download.assert_called_once()

    def test_album_reply_cannot_bypass_single_photo_requirement(self):
        update = photo("")
        update["message"]["media_group_id"] = "album"
        self.send(update)
        self.send(self.reply("2300", target=update["message"]))
        self.assertFalse(Product.objects.exists())
        self.assertEqual(TelegramSameDayPost.objects.get().last_error, "single_photo_required")

    def test_withdrawn_caption_edit_and_duplicate_remain_hidden(self):
        self.send(photo())
        command = self.reply("كشيده\u200cشد!")
        self.send(command)
        self.assertEqual(self.send(command).json()["result"], "duplicate_ignored")
        update = photo("3000", update_id=30, edited=True)
        update["edited_message"]["edit_date"] = 1700000004
        self.send(update)
        self.assertEqual(self.product().status, Product.Status.WITHDRAWN)
        self.assertFalse(Product.objects.for_same_day().published().exists())

    def test_pending_photo_unauthorized_price_and_withdraw_cannot_mutate(self):
        self.send(photo(""))
        for text in ("2300", "کشیده شد", "فروخته شد"):
            update = self.reply(text)
            update["message"]["from"]["id"] = 999
            self.assertEqual(self.send(update).status_code, 403)
        self.assertFalse(Product.objects.exists())
        post = TelegramSameDayPost.objects.get()
        self.assertIsNone(post.withdrawn_at)
        self.assertIsNone(post.sold_at)

    def test_price_reply_transport_failure_retries_without_consuming(self):
        from main.telegram_same_day.client import TelegramTransportError
        self.send(photo(""))
        self.download.side_effect = TelegramTransportError("upstream unavailable")
        self.assertEqual(self.send(self.reply("2300")).status_code, 503)
        self.assertFalse(Product.objects.exists())
        self.download.side_effect = fixtures.image_file
        self.assertEqual(self.send(self.reply("2300")).json()["result"], "created")

    def test_check_accepts_group_only_configuration(self):
        from django.core.management import call_command
        from io import StringIO
        with override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_SAME_DAY_RELAY_URL=""):
            out = StringIO()
            call_command("telegram_same_day_webhook", "check", stdout=out)
            self.assertIn("configuration OK", out.getvalue())
