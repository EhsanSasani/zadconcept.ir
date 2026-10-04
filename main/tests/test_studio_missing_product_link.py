from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from main.models import Category, Product, TelegramSameDayPost

class MissingProductLinkTests(TestCase):
    def setUp(self):
        category=Category.objects.create(name='گل',slug='link-test',section='flowers')
        self.product=Product.objects.create(name='1081',category=category,catalog_scope='same_day')
        TelegramSameDayPost.objects.create(product=self.product,telegram_chat_id=-123,telegram_message_id=318,studio_error='missing_fields')
        self.target=reverse('admin:main_samedayflower_change',args=[self.product.pk])
    def test_manager_link_and_destination(self):
        user=get_user_model().objects.create_superuser('link-admin',password='pass')
        self.client.force_login(user)
        response=self.client.get(reverse('studio_settings'))
        self.assertContains(response,self.target)
        self.assertNotContains(response,reverse('admin:main_product_change',args=[self.product.pk]))
        self.assertEqual(self.client.get(self.target).status_code,200)
    def test_general_product_permission_does_not_grant_proxy_access(self):
        user=get_user_model().objects.create_user('reader',is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(codename__in=['view_studioproduct','change_product']))
        self.client.force_login(user)
        self.assertNotContains(self.client.get(reverse('studio_settings')),self.target)
        user.user_permissions.add(Permission.objects.get(codename='view_samedayflower'))
        self.assertContains(self.client.get(reverse('studio_settings')),self.target)
        self.assertEqual(self.client.get(self.target).status_code,200)
