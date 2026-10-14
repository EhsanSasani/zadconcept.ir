from datetime import timedelta
from django.urls import reverse
from main.tests.test_studio_event_statistics import StudioEventStatisticsTests

class ManagerOverviewTests(StudioEventStatisticsTests):
    def test_production_value_is_removed_and_old_bookmarks_go_to_production_count(self):
        self.row()
        for name in ('studio_dashboard','studio_products','studio_analytics'):
            response=self.client.get(reverse(name))
            self.assertEqual(response.status_code,200)
            self.assertNotContains(response,'ارزش تولید')
        dashboard=self.client.get(reverse('studio_dashboard'))
        self.assertNotIn('total_value',dashboard.context['metric_links'])
        self.assertNotIn('total_value',dashboard.context['stats'])
        response=self.client.get(reverse('studio_metric',args=['total_value']),{'period':'7'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.url,reverse('studio_metric',args=['produced'])+'?period=7')

    def test_withdrawal_split_uses_withdrawal_date_and_current_status(self):
        self.row(produced=self.clock-timedelta(days=20),status='WITHDRAWN',event=self.clock)
        self.row(status='WITHDRAWN',event=self.clock)
        self.row(production='CUSTOM',status='WITHDRAWN',event=self.clock)
        self.row(status='WITHDRAWN',event=self.clock-timedelta(days=1))
        self.row(status='SOLD',event=self.clock)
        self.row()
        response=self.client.get(reverse('studio_metric',args=['withdrawn']),{'period':'today'})
        self.assertEqual(response.context['production_counts'],{'daily':2,'custom':1,'misc':0})
        self.assertEqual(response.context['total'],3)
        self.assertNotContains(response,'class="panel metric-chart"')
        self.assertContains(response,'تفکیک تعداد محصولات کشیده‌شده در بازهٔ انتخابی')

    def test_sales_split_counts_sale_events_and_includes_misc_without_old_sales(self):
        from main.models import StudioProduct
        self.row(produced=self.clock-timedelta(days=20),status='SOLD',event=self.clock)
        self.row(production='CUSTOM',status='SOLD',event=self.clock)
        self.row(status='SOLD',event=self.clock-timedelta(days=1))
        self.row()
        StudioProduct.objects.create(production_type='MISC',product_type='other',status='SOLD',
            produced_at=self.clock,sold_at=self.clock,price=100,notes='متفرقه')
        response=self.client.get(reverse('studio_metric',args=['sold']),{'period':'today'})
        self.assertEqual(response.context['production_counts'],{'daily':1,'custom':1,'misc':1})
        self.assertEqual(response.context['total'],3)
        self.assertNotContains(response,'class="panel metric-chart"')
        self.assertContains(response,'تفکیک تعداد فروش در بازهٔ انتخابی')

    def test_production_split_counts_whole_period_and_keeps_misc_sales_out_of_production(self):
        from main.models import StudioProduct
        for _ in range(22): self.row()
        self.row(production='CUSTOM',status='SOLD',event=self.clock)
        self.row(produced=self.clock-timedelta(days=1))
        StudioProduct.objects.create(production_type='MISC',product_type='other',status='SOLD',
            produced_at=self.clock,sold_at=self.clock,price=100,notes='فروش متفرقه')
        response=self.client.get(reverse('studio_metric',args=['produced']),{'period':'today','page':2})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['production_counts'],{'daily':22,'custom':1,'misc':0})
        self.assertEqual(response.context['total'],23)
        self.assertEqual(len(response.context['page']),3)
        self.assertNotContains(response,'class="panel metric-chart"')
        self.assertContains(response,'تفکیک تعداد تولید در بازهٔ انتخابی')

    def test_dashboard_team_includes_only_production_or_valid_sales_in_period(self):
        from main.models import Florist
        idle = Florist.objects.create(name='بدون فعالیت', code='idle')
        withdrawal_only = Florist.objects.create(name='فقط خروج', code='withdrawal-only')
        self.row(florist=withdrawal_only, produced=self.clock-timedelta(days=10),
                 status='WITHDRAWN', event=self.clock)
        self.row(florist=self.florist)
        self.other.is_active = False
        self.other.save()
        self.row(florist=self.other, produced=self.clock-timedelta(days=10),
                 status='SOLD', event=self.clock)
        self.row(florist=idle, produced=self.clock-timedelta(days=2))
        response = self.client.get(reverse('studio_dashboard'), {'period':'today'})
        rows = {item['florist'].pk:item['stats'] for item in response.context['florists']}
        self.assertEqual(set(rows), {self.florist.pk, self.other.pk})
        self.assertEqual(rows[self.other.pk]['produced'], 0)
        self.assertEqual(rows[self.other.pk]['sold'], 1)

    def test_yesterday_excludes_today_and_preserves_drilldown(self):
        yesterday = self.clock-timedelta(days=1)
        self.row(produced=yesterday, status='SOLD', event=yesterday, price=2300000)
        self.row(status='SOLD', event=self.clock, price=9900000)
        response = self.client.get(reverse('studio_dashboard'), {'period':'yesterday', 'start_jalali':'bad'})
        period = response.context['period']
        self.assertEqual(period['start'], yesterday.date())
        self.assertEqual(period['end'], yesterday.date())
        self.assertEqual(response.context['stats']['sold_value'], 2300000)
        self.assertFalse(period['error'])
        self.assertIn('period=yesterday', response.context['metric_links']['sold_value'])

    def test_vitrine_includes_old_daily_stock_but_excludes_custom_and_sold(self):
        old = self.row(produced=self.clock-timedelta(days=40))
        self.row(production='CUSTOM')
        self.row(status='SOLD', event=self.clock)
        response=self.client.get(reverse('studio_dashboard'), {'period':'today'})
        self.assertEqual(response.context['vitrine_count'], 1)
        self.assertEqual(list(response.context['vitrine']), [old])
        self.assertEqual(response.context['stats']['available'], 1)
        self.assertNotContains(response, 'میانگین زمان فروش')
        self.assertNotContains(response, 'id="trend-chart"')
        self.assertEqual(len(response.context['metric_links']), 5)

    def test_sale_drilldown_filters_sale_day_and_preserves_amount(self):
        row=self.row(produced=self.clock-timedelta(days=2), status='SOLD', event=self.clock, price=2500000)
        self.row(status='SOLD', event=self.clock-timedelta(days=1))
        response=self.client.get(reverse('studio_metric', args=['sold_value']), {'period':'today'})
        self.assertEqual(response.context['total'], 2500000)
        self.assertEqual([r.pk for r in response.context['page']], [row.pk])
        self.assertEqual(response.context['chart_rows'][0]['value'], 2500000)

    def test_metric_permission_and_unknown_key(self):
        self.assertEqual(self.client.get(reverse('studio_metric',args=['invalid'])).status_code,404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('studio_metric',args=['sold'])).status_code,302)

    def test_all_metric_pages_render_and_full_period_chart(self):
        self.row()
        for key in ['produced','sold','withdrawn','available','sold_value']:
            response=self.client.get(reverse('studio_metric',args=[key]),{'period':'90'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(len(response.context['chart_rows']),0 if key=='available' else 90)
