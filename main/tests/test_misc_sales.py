from datetime import date, datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from main.models import StudioProduct, StudioSalesAudit, StudioDelivery
from main.sales_service import apply_sales_action, version
from django.core.exceptions import ValidationError


class MiscSalesTests(TestCase):
    def setUp(self):
        self.seller = get_user_model().objects.create_user('counter')
        self.seller.user_permissions.add(Permission.objects.get(codename='use_sales_workspace'))
        self.client.force_login(self.seller)
        self.clock = patch('django.utils.timezone.now', return_value=datetime(2026, 10, 6, 12, tzinfo=ZoneInfo('Asia/Tehran')))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def data(self, url=None, **changes):
        response = self.client.get(url or reverse('sales_misc'))
        data = dict(response.context['form'].initial)
        data.update(date='۱۴۰۵/۰۷/۱۴', description='۳ شاخه رز با کاغذپیچی', price='۲.۳۰۰.۰۰۰')
        data.update(changes)
        return data

    def create(self, **changes):
        self.assertEqual(self.client.post(reverse('sales_misc'), self.data(**changes)).status_code, 302)
        return StudioProduct.objects.latest('pk')

    def test_four_fields_and_repeat_submission(self):
        data = self.data()
        for _ in range(2):
            self.assertEqual(self.client.post(reverse('sales_misc'), data).status_code, 302)
        record = StudioProduct.objects.get()
        self.assertEqual(record.price, 2300000)
        self.assertEqual(record.display_name, data['description'])
        self.assertIsNone(record.florist_id)
        self.assertIsNone(record.product_id)
        self.assertEqual(record.status, 'SOLD')
        self.assertEqual(StudioSalesAudit.objects.count(), 1)
        self.assertFalse(StudioDelivery.objects.exists())
        form = self.client.get(reverse('sales_misc')).context['form']
        self.assertEqual(form.initial['date'], data['date'])
        self.assertNotIn('description', form.initial)

    def test_backdate_edit_moves_revenue_between_periods(self):
        record = self.create()
        url = reverse('sales_misc_edit', args=[record.pk])
        old = self.data(url, date='۱۴۰۵/۰۷/۱۳', price='1,200,000')
        self.assertEqual(self.client.post(url, old).status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.sold_at.astimezone(ZoneInfo('Asia/Tehran')).date(), date(2026, 10, 5))
        self.assertEqual(self.client.get(reverse('sales_home')).context['stats']['value'], 0)
        self.assertEqual(self.client.post(url, old).status_code, 400)
        self.assertEqual(record.sales_audits.count(), 2)

    def test_reports_include_sales_without_production_or_florist(self):
        record = self.create()
        admin = get_user_model().objects.create_superuser('manager', password='test')
        self.client.force_login(admin)
        for name in ['studio_dashboard', 'studio_analytics']:
            response = self.client.get(reverse(name), {'period': 'today'})
            self.assertEqual(response.status_code, 200)
            stats = response.context['stats']
            self.assertEqual((stats['sold'], stats['sold_value'], stats['misc_sales']), (1, 2300000, 2300000))
            self.assertEqual((stats['produced'], stats['total_value']), (0, 0))
            self.assertEqual(response.context['chart'][-1]['sold'], 1)
            self.assertEqual(response.context['chart'][-1]['produced'], 0)
        for metric, total in [('sold_value', 2300000), ('sold', 1), ('produced', 0), ('total_value', 0)]:
            response = self.client.get(reverse('studio_metric', args=[metric]), {'period': 'today'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['total'], total)
        for name, args in [('studio_products', []), ('studio_product_detail', [record.pk]), ('sales_history', [])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_invalid_input_and_foreign_token_do_not_write(self):
        for changes in [{'date': '۱۴۰۴/۱۲/۳۰'}, {'date': '۱۴۰۵/۰۷/۲۰'}, {'price': '0'}, {'price': '-5'},
                        {'price': '1000000000000'}, {'description': '   '}, {'token': 'forged'}]:
            with self.subTest(changes=changes):
                self.assertEqual(self.client.post(reverse('sales_misc'), self.data(**changes)).status_code, 400)
        data = self.data()
        other = get_user_model().objects.create_user('other')
        other.user_permissions.add(Permission.objects.get(codename='use_sales_workspace'))
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse('sales_misc'), data).status_code, 400)
        self.assertFalse(StudioProduct.objects.exists())

    def test_denied_user_and_generic_action(self):
        record = self.create()
        with self.assertRaises(ValidationError):
            apply_sales_action(pk=record.pk, actor=self.seller, expected_version=version(record), action='restore', reason='test')
        self.seller.user_permissions.clear()
        self.assertEqual(self.client.get(reverse('sales_misc')).status_code, 403)
        self.assertEqual(self.client.post(reverse('sales_misc'), {}).status_code, 403)

    def test_database_keeps_regular_production_constraints(self):
        record = self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudioProduct.objects.filter(pk=record.pk).update(production_type='DAILY')
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudioProduct.objects.filter(pk=record.pk).update(status='AVAILABLE')

    def test_deleted_sales_drop_out_of_reports(self):
        record = self.create()
        from main.studio_delivery import soft_delete_product
        admin = get_user_model().objects.create_superuser('deleting-manager', password='test')
        soft_delete_product(record, actor=admin, reason='ثبت اشتباه')
        self.assertEqual(self.client.get(reverse('sales_home')).context['stats']['value'], 0)
        self.assertEqual(self.client.get(reverse('sales_misc')).context['page'].paginator.count, 0)

    def test_search_description_id_and_separate_submission(self):
        first = self.create()
        second = self.create(description='کاغذپیچی')
        self.assertNotEqual(first.pk, second.pk)
        for query in [str(first.pk), '۳ شاخه رز']:
            response = self.client.get(reverse('sales_home'), {'tab': 'misc', 'q': query})
            self.assertEqual([row.pk for row in response.context['page']], [first.pk])
