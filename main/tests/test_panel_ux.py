"""Rendered staff forms keep actionable, linked validation feedback."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

class PanelFormErrorTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser(username='synthetic-ux-admin',password='synthetic-only')
        self.client.force_login(self.user)

    def test_invalid_material_conversion_has_linked_actionable_error(self):
        response=self.client.post(reverse('procurement_material_add'),{
            'name':'Synthetic UX material','base_unit':'stem','purchase_unit':'pack',
            'units_per_purchase':'-1','default_unit_price':'123','is_active':'on'})
        self.assertEqual(response.status_code,400)
        self.assertContains(response,'aria-invalid="true"',status_code=400)
        self.assertContains(response,'aria-describedby="id_units_per_purchase_helptext id_units_per_purchase_error"',status_code=400)
        self.assertContains(response,'id="id_units_per_purchase_error"',status_code=400)
        self.assertContains(response,'id="id_units_per_purchase_helptext"',status_code=400)

    def test_invalid_account_password_has_matching_error_description_id(self):
        response=self.client.post(reverse('studio_account_add'),{
            'username':'synthetic-ux-new','first_name':'Synthetic','last_name':'Reviewer',
            'roles':['sales'],'password1':'synthetic-test-password','password2':'different-test-password','is_active':'on'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'aria-invalid="true"')
        self.assertContains(response,'id="id_password2_error"')
        self.assertFalse(get_user_model().objects.filter(username='synthetic-ux-new').exists())

    def test_mobile_sort_uses_same_server_side_table_navigation_as_desktop(self):
        response=self.client.get(reverse('studio_products')+'?period=30&q=synthetic')
        self.assertContains(response,'data-sort-link data-sort-key="price"')
        self.assertContains(response,'data-sort-link data-sort-key="produced"')
        self.assertContains(response,'q=synthetic')


class PanelDescriptionIntegrityTests(TestCase):
    def setUp(self):
        from main.models import Florist,StudioProduct
        self.user=get_user_model().objects.create_superuser(username='synthetic-description-admin',password='synthetic-only')
        florist=Florist.objects.create(user=self.user,name='Synthetic florist',code='synthetic-description')
        self.product=StudioProduct.objects.create(florist=florist,product_type='bouquet',production_type='CUSTOM',
            status='AVAILABLE',source='DASHBOARD',price=250000,image='synthetic/panel.jpg')
        self.client.force_login(self.user)

    def assert_descriptions_resolve(self,response):
        from html.parser import HTMLParser
        class References(HTMLParser):
            def __init__(self):super().__init__();self.ids=[];self.refs=[]
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if attrs.get('id'):self.ids.append(attrs['id'])
                self.refs.extend(attrs.get('aria-describedby','').split())
        parser=References();parser.feed(response.content.decode())
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        self.assertEqual(set(parser.refs)-set(parser.ids),set())

    def test_sales_edit_help_and_failed_sale_error_resolve(self):
        endpoint=reverse('sales_detail',args=[self.product.pk])
        self.assert_descriptions_resolve(self.client.get(endpoint))
        from main.sales_service import version
        response=self.client.post(endpoint,{'action':'sell','sale_price':'12.5','reason':'synthetic invalid amount','version':version(self.product)})
        self.assertEqual(response.status_code,400)
        self.assertContains(response,'id="sale-price-error"',status_code=400)
        self.assertContains(response,'aria-describedby="sale-price-error"',status_code=400)
        self.assert_descriptions_resolve(response)
        self.product.refresh_from_db();self.assertEqual(self.product.status,'AVAILABLE');self.assertEqual(self.product.price,250000)

    def test_waste_formset_descriptions_resolve_for_every_row(self):
        response=self.client.get(reverse('procurement_waste_add'))
        self.assertEqual(response.status_code,200);self.assert_descriptions_resolve(response)

    def test_profile_password_help_and_errors_resolve_without_changing_credentials(self):
        endpoint=reverse('team_profile');before=self.user.password
        self.assert_descriptions_resolve(self.client.get(endpoint))
        response=self.client.post(endpoint,{'action':'password','old_password':'wrong-synthetic-password',
            'new_password1':'synthetic-new-password-unique','new_password2':'mismatched-password'})
        self.assertEqual(response.status_code,200);self.assert_descriptions_resolve(response)
        self.user.refresh_from_db();self.assertEqual(self.user.password,before)


class SettingsNavigationTests(TestCase):
    def setUp(self):
        user=get_user_model().objects.create_superuser(username='synthetic-settings-admin',password='synthetic-only')
        self.client.force_login(user)

    def test_empty_settings_does_not_offer_dead_report_anchors(self):
        response=self.client.get(reverse('studio_settings'))
        self.assertNotContains(response,'href="#issues-table"')
        self.assertNotContains(response,'href="#missing-table"')

    def test_existing_issues_retain_a_real_jump_destination(self):
        from main.models import StudioIngestionIssue
        StudioIngestionIssue.objects.create(telegram_chat_id=-900001,telegram_message_id=1,reason='Synthetic review issue')
        response=self.client.get(reverse('studio_settings'))
        self.assertContains(response,'href="#issues-table"')
        self.assertContains(response,'id="issues-table"')
        self.assertNotContains(response,'href="#missing-table"')
