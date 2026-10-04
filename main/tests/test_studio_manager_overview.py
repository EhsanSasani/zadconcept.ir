from datetime import timedelta
from django.urls import reverse
from main.tests.test_studio_event_statistics import StudioEventStatisticsTests

class ManagerOverviewTests(StudioEventStatisticsTests):
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
        self.assertEqual(len(response.context['metric_links']), 6)

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
        for key in ['produced','sold','withdrawn','available','total_value','sold_value']:
            response=self.client.get(reverse('studio_metric',args=[key]),{'period':'90'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(len(response.context['chart_rows']),0 if key=='available' else 90)
