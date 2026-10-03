from datetime import datetime, timedelta, timezone as utc_timezone
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.models import Florist, StudioProduct
from main.studio_views import _activity, _chart, _period, _stats
from django.test import RequestFactory


class StudioEventStatisticsTests(TestCase):
    def setUp(self):
        self.clock = datetime(2026, 10, 3, 12, tzinfo=ZoneInfo('Asia/Tehran'))
        self.time = patch('django.utils.timezone.now', return_value=self.clock)
        self.time.start()
        self.addCleanup(self.time.stop)
        self.zone = timezone.override('Asia/Tehran')
        self.zone.__enter__()
        self.addCleanup(self.zone.__exit__, None, None, None)
        self.admin = get_user_model().objects.create_superuser('event-stats', password='pass')
        self.client.force_login(self.admin)
        self.florist = Florist.objects.create(name='آزمایش', code='events')
        self.other = Florist.objects.create(name='دیگری', code='other-events')
        self.number = 0

    def row(self, *, produced=None, status='AVAILABLE', event=None, price=1000000,
            florist=None, production='DAILY', product_type='box'):
        self.number += 1
        return StudioProduct.objects.create(
            factor_code=f'EVENT-{self.number}', florist=florist or self.florist,
            product_type=product_type, production_type=production, price=price,
            status=status, produced_at=produced or self.clock, source='DASHBOARD',
            image='studio/test.webp', sold_at=event if status == 'SOLD' else None,
            withdrawn_at=event if status == 'WITHDRAWN' else None)

    def period(self, **params):
        return _period(RequestFactory().get('/', params or {'period': 'today'}))

    def stats(self, period=None):
        period = period or self.period()
        return _stats(_activity(period), period)

    def test_yesterdays_production_sold_today_counts_on_sale_day_in_every_report(self):
        self.row(produced=self.clock - timedelta(days=1), status='SOLD', event=self.clock, price=2500000)
        paths = [('studio_dashboard', []), ('studio_analytics', []),
                 ('studio_florist_profile', [self.florist.pk]), ('studio_products', [])]
        for name, args in paths:
            with self.subTest(view=name):
                response = self.client.get(reverse(name, args=args), {'period': 'today'})
                self.assertEqual(response.status_code, 200)
                stats = response.context['summary' if name == 'studio_products' else 'stats']
                self.assertEqual((stats['produced'], stats['sold'], stats['sold_value']), (0, 1, Decimal(2500000)))
                self.assertEqual(stats['average_days'], 1.0)
        response = self.client.get(reverse('studio_florists'), {'period': 'today'})
        own = next(item for item in response.context['rows'] if item['florist'] == self.florist)
        self.assertEqual(own['stats']['sold'], 1)
        yesterday = self.clock.date() - timedelta(days=1)
        response = self.client.get(reverse('studio_dashboard'), {
            'period': 'custom', 'start': yesterday.isoformat(), 'end': yesterday.isoformat()})
        self.assertEqual(response.context['stats']['produced'], 1)
        self.assertEqual(response.context['stats']['sold'], 0)
        self.assertEqual(response.context['stats']['sold_value'], 0)
        self.assertEqual(response.context['comparisons']['sold'], None)

    def test_yesterdays_production_withdrawn_today_uses_withdrawal_time(self):
        self.row(produced=self.clock - timedelta(days=3), status='WITHDRAWN', event=self.clock)
        self.assertEqual((self.stats()['produced'], self.stats()['withdrawn']), (0, 1))
        day = self.clock.date() - timedelta(days=3)
        prior = self.period(period='custom', start=str(day), end=str(day))
        self.assertEqual((_stats(_activity(prior), prior)['produced'],
                          _stats(_activity(prior), prior)['withdrawn']), (1, 0))
        response = self.client.get(reverse('studio_analytics'), {'period': 'today'})
        self.assertEqual(response.context['by_type'][0]['withdrawn'], 1)

    def test_tehran_midnight_is_inclusive_and_next_midnight_exclusive(self):
        lower = datetime(2026, 10, 2, 20, 30, tzinfo=utc_timezone.utc)
        upper = lower + timedelta(days=1)
        for offset, price in ((-1, 100), (0, 200), (86399, 300), (86400, 400)):
            self.row(produced=lower - timedelta(days=4), status='SOLD',
                     event=lower + timedelta(seconds=offset), price=price)
        self.assertEqual((self.stats()['sold'], self.stats()['sold_value']), (2, 500))
        chart = _chart(_activity(self.period()), self.period())
        self.assertEqual(chart, [{'label': '2026-10-03', 'produced': 0, 'sold': 2, 'withdrawn': 0}])
        self.assertEqual(self.period()['upper'].astimezone(utc_timezone.utc), upper)

    def test_each_chart_series_uses_its_event_date(self):
        self.row(produced=self.clock - timedelta(days=1), status='SOLD', event=self.clock)
        self.row(produced=self.clock - timedelta(days=2), status='WITHDRAWN', event=self.clock)
        period = self.period(period='7')
        chart = _chart(_activity(period), period)
        self.assertEqual(chart[-1]['produced'], 0)
        self.assertEqual((chart[-1]['sold'], chart[-1]['withdrawn']), (1, 1))
        self.assertEqual((chart[-2]['produced'], chart[-2]['sold']), (1, 0))
        self.assertEqual((chart[-3]['produced'], chart[-3]['withdrawn']), (1, 0))

    def test_cohort_rate_remains_bounded_and_old_sales_are_not_double_counted(self):
        self.row(status='SOLD', event=self.clock)
        for _ in range(3):
            self.row(produced=self.clock - timedelta(days=40), status='SOLD', event=self.clock)
        stats = self.stats()
        self.assertEqual((stats['produced'], stats['sold'], stats['cohort_sold'], stats['sell_through']), (1, 4, 1, 100))
        response = self.client.get(reverse('studio_analytics'), {'period': 'today'})
        row = response.context['by_type'][0]
        self.assertEqual((row['produced'], row['sold'], row['sell_through']), (1, 4, 100))

    def test_filters_preserve_event_dates_and_deleted_rows_are_excluded(self):
        mine = self.row(produced=self.clock - timedelta(days=45), status='SOLD', event=self.clock)
        self.row(produced=self.clock - timedelta(days=45), status='SOLD', event=self.clock, florist=self.other)
        deleted = self.row(produced=self.clock - timedelta(days=45), status='SOLD', event=self.clock)
        StudioProduct.objects.filter(pk=deleted.pk).update(status='DELETED', deleted_at=self.clock)
        for name, args, params in (
            ('studio_florist_profile', [self.florist.pk], {'production_type': 'DAILY'}),
            ('studio_products', [], {'florist': self.florist.pk, 'status': 'SOLD', 'q': mine.factor_code}),
        ):
            response = self.client.get(reverse(name, args=args), {'period': 'today', **params})
            stats = response.context['summary' if name == 'studio_products' else 'stats']
            self.assertEqual((stats['sold'], stats['produced']), (1, 0))
        self.assertEqual(self.stats()['sold'], 2)
        self.assertEqual(self.client.get(reverse('studio_florist_profile', args=[self.florist.pk]),
                                        {'period': 'today', 'production_type': 'CUSTOM'}).context['stats']['sold'], 0)

    def test_week_month_quarter_and_custom_ranges_include_old_stock_events(self):
        self.row(produced=self.clock - timedelta(days=200), status='SOLD', event=self.clock)
        self.row(produced=self.clock - timedelta(days=200), status='WITHDRAWN', event=self.clock)
        for choice in ('today', '7', '30', '90', 'month', 'custom'):
            period = self.period(period=choice, start='2026-10-02', end='2026-10-03')
            stats = self.stats(period)
            self.assertEqual((stats['produced'], stats['sold'], stats['withdrawn']), (0, 1, 1))

    def test_previous_comparison_uses_previous_sale_event_not_production(self):
        for _ in range(2):
            self.row(produced=self.clock - timedelta(days=20), status='SOLD', event=self.clock)
        self.row(produced=self.clock - timedelta(days=20), status='SOLD', event=self.clock - timedelta(days=1))
        response = self.client.get(reverse('studio_dashboard'), {'period': 'today'})
        self.assertEqual(response.context['comparisons']['sold'], 100)

    def test_custom_same_day_sale_is_counted_once_without_mutating_data(self):
        row = self.row(status='SOLD', event=self.clock, production='CUSTOM')
        before = StudioProduct.objects.values().get(pk=row.pk)
        for _ in range(2):
            self.assertEqual((self.stats()['produced'], self.stats()['sold']), (1, 1))
        self.assertEqual(StudioProduct.objects.values().get(pk=row.pk), before)
