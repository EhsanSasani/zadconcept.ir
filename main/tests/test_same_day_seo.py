from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from main.models import Category, Product
from main.seo import absolute_site_url, product_node
from .test_seo import graph_for


@override_settings(ZAD_SITE_URL="https://www.zadconcept.ir")
class SameDaySeoTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="گل آماده", slug="seo-ready", section="flowers")
        self.low = self.make("گل یک", 1450000)
        self.high = self.make("گل دو", 3500000)
        self.inquiry = self.make("گل استعلام", None, pricing_type=Product.PricingType.INQUIRY)
        self.url = reverse("flowers_same_day")

    def make(self, name, price, **overrides):
        data = dict(name=name, category=self.category, price=price,
                    pricing_type=Product.PricingType.FIXED,
                    catalog_scope=Product.CatalogScope.SAME_DAY,
                    publish_status=Product.PublishStatus.PUBLISHED)
        data.update(overrides)
        return Product.objects.create(**data)

    def test_summary_excludes_unavailable_draft_and_general_products(self):
        for state in (Product.Status.SOLD, Product.Status.WITHDRAWN):
            self.make(str(state), 99000000, status=state)
        self.make("ناموجود", 99000000, stock_status=Product.StockStatus.OUT_OF_STOCK)
        self.make("پیش سفارش", 99000000, stock_status=Product.StockStatus.PREORDER)
        self.make("پیش نویس", 99000000, publish_status=Product.PublishStatus.DRAFT)
        self.make("کاتالوگ", 99000000, catalog_scope=Product.CatalogScope.GENERAL)
        response = self.client.get(self.url)
        self.assertEqual(response.context['same_day_count'], 3)
        self.assertEqual(response.context['same_day_priced_count'], 2)
        self.assertEqual(response.context['same_day_cheapest'].pk, self.low.pk)
        self.assertEqual(response.context['same_day_most_expensive'].pk, self.high.pk)
        self.assertContains(response, '1,450,000 تومان')
        self.assertNotContains(response, '99,000,000')

    def test_schema_matches_displayed_order_and_canonical_under_query(self):
        response = self.client.get(self.url+'?sort=price_asc')
        graph = graph_for(response)
        listing = next(n for n in graph if n['@type'] == 'ItemList')
        products = list(response.context['items'])
        self.assertEqual([p.pk for p in products], [self.high.pk,self.low.pk,self.inquiry.pk])
        self.assertEqual(listing['numberOfItems'],len(products))
        self.assertEqual([i['url'] for i in listing['itemListElement']],
                         [absolute_site_url(p.get_absolute_url()) for p in products])
        self.assertEqual([i['position'] for i in listing['itemListElement']],[1,2,3])
        page = next(n for n in graph if n['@type']=='CollectionPage')
        self.assertEqual(page['mainEntity']['@id'],listing['@id'])
        self.assertEqual(response.context['canonical_url'],absolute_site_url(self.url))
        self.assertEqual(response.context['robots_content'],'noindex,follow')
        self.assertFalse(any(n['@type'] in ('Product','AggregateOffer','FAQPage') for n in graph))
        self.assertContains(response,'aria-label="Breadcrumb"')

    def test_empty_page_keeps_guide_canonical_and_zero_item_list(self):
        Product.objects.all().update(status=Product.Status.SOLD)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'فعلاً محصولی برای ارسال امروز موجود نیست.')
        self.assertContains(response,'پرسش‌های خرید گل آماده')
        self.assertNotContains(response,'class="same-day-summary"')
        self.assertEqual(response.context['robots_content'],'index,follow')
        listing=next(n for n in graph_for(response) if n['@type']=='ItemList')
        self.assertEqual(listing['itemListElement'],[])
        self.assertEqual(listing['numberOfItems'],0)

    def test_all_inquiry_shows_no_numeric_range(self):
        Product.objects.all().update(pricing_type=Product.PricingType.INQUIRY)
        response=self.client.get(self.url)
        self.assertEqual(response.context['same_day_priced_count'],0)
        self.assertIsNone(response.context['same_day_cheapest'])
        self.assertContains(response,'برای قیمت گزینه‌های موجود، با زاد تماس بگیرید.')

    def test_count_and_range_refresh_after_sale_and_deletion(self):
        self.high.status=Product.Status.SOLD
        self.high.save(update_fields=['status'])
        self.inquiry.delete()
        response=self.client.get(self.url)
        self.assertEqual(response.context['same_day_count'],1)
        self.assertEqual(response.context['same_day_most_expensive'].pk,self.low.pk)

    def test_one_h1_with_and_without_managed_hero_even_blank_title(self):
        for hero in (None,{'has_managed_site_hero':True,'page_hero_style_class':'hero-style-test',
                           'page_hero_title':'عنوان سفارشی', 'page_hero_image':'main/img/hero-about.webp'},
                      {'has_managed_site_hero':True,'page_hero_style_class':'hero-style-test','page_hero_title':''}):
            with self.subTest(hero=hero), patch('main.views.catalog_views._get_site_hero',return_value=hero):
                response=self.client.get(self.url)
                html=response.content.decode()
                self.assertEqual(html.count('<h1'),1)
                self.assertIn('<h1>خرید گل آماده برای ارسال امروز در مشهد</h1>',html)
                self.assertTemplateUsed(response, 'main/components/same_day_hero.html')
                self.assertIn('zad-display-v1-1672.webp', html)
                if hero and hero['page_hero_title']:
                    self.assertNotIn('عنوان سفارشی',html)

    def test_product_offer_keeps_real_toman_to_rial_conversion(self):
        node=product_node(self.low)
        self.assertEqual(node['offers']['price'],'14500000')
        self.assertEqual(node['offers']['priceCurrency'],'IRR')
        self.assertEqual(node['offers']['availability'],'https://schema.org/InStock')

    def test_item_name_cannot_break_json_script(self):
        self.low.name='</script><script>alert(1)</script>'
        self.low.save(update_fields=['name'])
        response=self.client.get(self.url)
        self.assertTrue(any(n['@type']=='ItemList' for n in graph_for(response)))
        self.assertNotContains(response,'<script>alert(1)</script>')
