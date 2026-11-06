"""Shared staff navigation remains scoped and keeps server-side fallback links."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from main.models import Florist,StudioProduct


class PanelNavigationIntegrationTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='navigation-multi-role')
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='main'))
        self.florist=Florist.objects.create(user=self.user,name='آزمایشی',code='navigation')
        self.client.force_login(self.user)

    def test_all_four_workspaces_load_navigation_before_their_existing_scripts(self):
        for route,script in [('studio_products','manager-app.js'),('sales_home','sales.js'),
                             ('procurement_home','procurement.js'),('team_home','team.js')]:
            with self.subTest(route=route):
                response=self.client.get(reverse(route));self.assertEqual(response.status_code,200)
                html=response.content.decode()
                self.assertIn(f'data-panel-user="{self.user.pk}"',html)
                self.assertLess(html.index('panel-navigation.js'),html.index(script))

    def test_public_pages_do_not_load_private_navigation_and_login_clears_identity_scope(self):
        self.client.logout()
        response=self.client.get(reverse('index'))
        self.assertNotContains(response,'panel-navigation.js')
        response=self.client.get(reverse('studio_login'))
        self.assertContains(response,'data-panel-user=""')

    def test_material_cancel_participates_in_parent_navigation_with_a_server_fallback(self):
        response=self.client.get(reverse('procurement_material_add'))
        self.assertContains(response,'class="proc-btn proc-secondary" data-panel-back')
        self.assertContains(response,f'href="{reverse("procurement_materials")}"')

    def test_direct_product_entry_retains_a_real_server_side_back_link(self):
        product=StudioProduct.objects.create(florist=self.florist,product_type='bouquet',
            production_type='CUSTOM',price=100000,status='AVAILABLE',source='DASHBOARD',image='synthetic/navigation.jpg')
        response=self.client.get(reverse('sales_detail',args=[product.pk]))
        self.assertContains(response,f'class="panel-back" href="{reverse("sales_home")}"')


class SafePanelReturnTests(TestCase):
    def test_only_resolved_allowlisted_relative_destinations_are_accepted(self):
        from django.test import RequestFactory
        from main.panel_navigation import return_location, PRODUCT_RETURN_ROUTES
        fallback=reverse('studio_products')
        factory=RequestFactory()
        safe=fallback+'?q=synthetic&page=2&sort=price'
        for value in [safe, reverse('studio_metric',args=['sold'])+'?period=30']:
            with self.subTest(value=value):
                self.assertEqual(return_location(factory.post('/',{'return_to':value}),
                    'studio_products',PRODUCT_RETURN_ROUTES),value)
        for value in ['https://evil.test/studio/products/','//evil.test/studio/products/',
                      '/\\evil.test/studio/products/','/studio/products/#fragment',
                      '/studio/products/?q=\r\nLocation:evil', '/unknown/',
                      '/sales/', '/studio/logout/', '/studio/products/?q='+'x'*2050,
                      ' /studio/products/', '/studio/products/%0d%0a']:
            with self.subTest(value=value):
                self.assertEqual(return_location(factory.post('/',{'return_to':value}),
                    'studio_products',PRODUCT_RETURN_ROUTES),fallback)


class ProductReturnIntegrationTests(TestCase):
    setUp = PanelNavigationIntegrationTests.setUp
    def test_status_post_returns_to_exact_list_without_changing_authorization(self):
        product=StudioProduct.objects.create(florist=self.florist,product_type='bouquet',
            production_type='CUSTOM',price=100000,status='AVAILABLE',source='DASHBOARD',image='synthetic/navigation.jpg')
        destination=reverse('studio_products')+'?q=synthetic&page=2'
        endpoint=reverse('studio_product_status',args=[product.pk])
        response=self.client.post(endpoint,{'status':'WITHDRAWN','return_to':destination})
        self.assertRedirects(response,destination,fetch_redirect_response=False)
        product.refresh_from_db();self.assertEqual(product.status,'WITHDRAWN')
        outsider=get_user_model().objects.create_user(username='no-panel-permission')
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(endpoint,{'status':'SOLD','return_to':destination}).status_code,403)
        product.refresh_from_db();self.assertEqual(product.status,'WITHDRAWN')

    def test_return_hint_does_not_bypass_csrf_or_allow_external_redirects(self):
        from django.test import Client
        product=StudioProduct.objects.create(florist=self.florist,product_type='bouquet',
            production_type='CUSTOM',price=100000,status='AVAILABLE',source='DASHBOARD',image='synthetic/navigation.jpg')
        endpoint=reverse('studio_product_status',args=[product.pk])
        csrf_client=Client(enforce_csrf_checks=True);csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(endpoint,{'status':'WITHDRAWN','return_to':'/studio/products/'}).status_code,403)
        product.refresh_from_db();self.assertEqual(product.status,'AVAILABLE')
        response=self.client.post(endpoint,{'status':'WITHDRAWN','return_to':'//evil.test/studio/products/'})
        self.assertRedirects(response,reverse('studio_products'),fetch_redirect_response=False)
