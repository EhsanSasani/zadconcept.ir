from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from main.models import Florist, StudioProduct, StudioDelivery

class ManagerAppTests(TestCase):
    def setUp(self):
        self.manager=get_user_model().objects.create_user('reader',password='pass')
        self.manager.user_permissions.add(Permission.objects.get(codename='view_studioproduct'))
        self.florist=Florist.objects.create(name='آزمایش',code='app-qa')
        self.row=StudioProduct.objects.create(factor_code='APP-1',florist=self.florist,
            product_type='box',production_type='DAILY',source='DASHBOARD',price=2500000,
            image='studio/sample.webp',status='AVAILABLE',produced_at=timezone.now()-timedelta(days=2))
        self.client.force_login(self.manager)

    def test_readonly_detail_has_no_creator_and_no_privileged_action(self):
        response=self.client.get(reverse('studio_product_detail',args=[self.row.pk]))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'ثبت خودکار / نامشخص')
        self.assertNotContains(response,reverse('studio_product_edit',args=[self.row.pk]))
        self.assertEqual(StudioDelivery.objects.count(),0)
        self.assertEqual(self.client.post(reverse('studio_product_status',args=[self.row.pk]),{'status':'SOLD'}).status_code,403)

    def test_detail_permission_boundary(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('studio_product_detail',args=[self.row.pk])).status_code,302)
        user=get_user_model().objects.create_user('maker')
        self.florist.user=user;self.florist.save(update_fields=['user'])
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('studio_product_detail',args=[self.row.pk])).status_code,403)

    def test_overview_limits_preview_without_losing_inventory(self):
        for n in range(5):
            StudioProduct.objects.create(factor_code=f'APP-{n+2}',florist=self.florist,
                product_type='box',production_type='DAILY',source='DASHBOARD',price=1000,
                image='studio/sample.webp',status='AVAILABLE')
        response=self.client.get(reverse('studio_dashboard'),{'period':'today'})
        self.assertEqual(response.context['vitrine_count'],6)
        self.assertEqual(len(response.context['vitrine']),4)
        self.assertEqual(len(response.context['mobile_nav']),5)
        self.assertNotContains(response,'میانگین زمان فروش')
        self.assertEqual(StudioDelivery.objects.count(),0)

    def test_detail_escapes_notes_and_retains_deleted_record(self):
        self.row.notes='<script>alert(1)</script>'
        self.row.status='DELETED';self.row.deleted_at=timezone.now();self.row.deletion_reason='ثبت اشتباه'
        self.row.save()
        response=self.client.get(reverse('studio_product_detail',args=[self.row.pk]))
        self.assertContains(response,'&lt;script&gt;')
        self.assertContains(response,'ثبت اشتباه')
        self.assertNotContains(response,'<script>alert(1)</script>')

    def test_zero_production_is_not_zero_percent_performance(self):
        response=self.client.get(reverse('studio_florists'),{'period':'today'})
        self.assertContains(response,'—')

    def test_custom_delivery_labels_and_no_admin_links_for_reader(self):
        self.row.production_type='CUSTOM';self.row.status='SOLD';self.row.sold_at=timezone.now();self.row.save()
        StudioDelivery.objects.create(record=self.row,action='PUBLISH',chat_id=-1234,status='UNCERTAIN')
        response=self.client.get(reverse('studio_deliveries'))
        self.assertContains(response,'گروه سفارشی')
        self.assertNotContains(response,'گروه آماده‌ها')
        self.assertNotContains(response,'name="action" value="retry_absent"')
        self.assertEqual(StudioDelivery.objects.get().status,'UNCERTAIN')
