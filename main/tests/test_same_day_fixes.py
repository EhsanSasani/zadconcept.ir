from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from main.models import Product, SameDayFlower, TelegramSameDayPost
from main.telegram_same_day.price import parse_group_price, PriceError
from . import test_telegram_group_products as group_fixtures
from .test_telegram_group_products import photo
from .test_telegram_same_day import GROUP
from . import test_same_day_catalog as catalog_fixtures


class ExpandedPriceTests(SimpleTestCase):
    def test_team_formats(self):
        for value in ('مبلغ ۲/۴۵۰', 'مبلغ: ٢/٤٥٠', 'مبلغ ۲ / ۴۵۰',
                      'بها: ۲۴۵۰', 'فی ۲۴۵۰', 'قیمت فروش: ۲۴۵۰',
                      'قیمت نهایی: ۲۴۵۰', 'دسته گل مبلغ ۲/۴۵۰',
                      'مبلغ:\n۲۴۵۰', '💰 مبلغ ۲/۴۵۰ t', '\u200fمبلغ ۲/۴۵۰',
                      '۲ میلیون و ۴۵۰ هزار تومان', 'مبلغ ۲ میلیون و ۴۵۰ هزار', '۲٫۴۵ میلیون تومن', '۲۴۵۰ هزار تومن', '۲,۴۵۰,۰۰۰ تومان'):
            with self.subTest(value=value):
                self.assertEqual(parse_group_price(value), 2450000)

    def test_decimal_shorthand_with_zero_fraction(self):
        self.assertEqual(parse_group_price("مبلغ ۲٫۰"), 2000000)
        self.assertEqual(parse_group_price("۲.۰ تومان"), 2)

    def test_ambiguous_amounts_rejected(self):
        for value in ('مبلغ توافقی', 'مبلغ ۲۴۵۰ یا ۲۵۰۰', 'مبلغ ۲۴۵۰\n۲۵۰۰',
                      'مبلغ ۲۴۵۰ ریال', 'مبلغ -۲۴۵۰', 'مبلغ ۰۹۱۲۳۴۵۶۷۸۹'):
            with self.subTest(value=value), self.assertRaises(PriceError):
                parse_group_price(value)


@override_settings(TELEGRAM_CHANNEL_ID="", TELEGRAM_DISCUSSION_GROUP_ID="",
                   TELEGRAM_SAME_DAY_GROUP_ID=str(GROUP), TELEGRAM_WEBHOOK_SECRET="test-secret")
class DeletionRegressionTests(TestCase):
    setUp = group_fixtures.GroupWorkflowTests.setUp
    send = group_fixtures.GroupWorkflowTests.send
    product = group_fixtures.GroupWorkflowTests.product
    reply = group_fixtures.GroupWorkflowTests.reply

    def test_admin_bulk_confirmation_and_delete_keeps_tombstone(self):
        self.send(photo())
        product = self.product()
        user = get_user_model().objects.create_superuser('delete-admin', 'admin@example.com', 'password')
        self.client.force_login(user)
        # This client is intentionally for the admin flow (webhook fixture enforces CSRF).
        from django.test import Client
        client = Client()
        client.force_login(user)
        url = reverse('admin:main_samedayflower_changelist')
        data = {'action': 'delete_selected', '_selected_action': [str(product.pk)]}
        confirmation = client.post(url, data)
        self.assertEqual(confirmation.status_code, 200)
        self.assertFalse(confirmation.context['protected'])
        self.assertContains(confirmation, 'name="post"')
        self.assertEqual(client.post(url, {**data, 'post': 'yes'}).status_code, 302)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())
        post = TelegramSameDayPost.objects.get()
        self.assertIsNone(post.product_id)
        self.assertIsNotNone(post.deleted_at)
        self.send(photo('3000', update_id=40, edited=True))
        self.send(self.reply('۴۰۰۰', update_id=50))
        self.assertFalse(Product.objects.exists())

    def test_individual_proxy_delete_preserves_identity(self):
        self.send(photo())
        SameDayFlower.objects.get(pk=self.product().pk).delete()
        self.assertIsNotNone(TelegramSameDayPost.objects.get().deleted_at)
        self.assertEqual(self.send(photo()).json()['result'], 'admin_deleted_ignored')
        self.assertFalse(Product.objects.exists())

    def test_amount_label_reply_publishes_pending_photo(self):
        self.send(photo(''))
        self.send(self.reply('مبلغ ۲/۴۵۰'))
        self.assertEqual(self.product().price, 2450000)


class PriceOrderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        catalog_fixtures.SameDayCatalogIsolationTests.setUpTestData.__func__(cls)

    def test_price_descending_overrides_manual_order_and_query(self):
        Product.objects.filter(pk=self.same_day.pk).update(price=1000000, sort_order=0)
        Product.objects.filter(pk=self.same_day_related.pk).update(price=3000000, sort_order=999)
        for query in ('', '?sort=price_asc'):
            response = self.client.get(reverse('flowers_same_day') + query)
            self.assertEqual(list(response.context['items'].values_list('pk', flat=True)),
                             [self.same_day_related.pk, self.same_day.pk])
