from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from main.admin_content import PageContentBlockAdminForm
from main.models import Category, Flower, PageContentBlock, Product, Story


class AdminWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser('workspace-admin', 'admin@example.invalid', 'test-password')
        cls.staff = get_user_model().objects.create_user('workspace-staff', password='test-password', is_staff=True)
        cls.category = Category.objects.create(name='گل تست', slug='workspace-flowers', section=Category.Section.FLOWERS)
        cls.product = Product.objects.create(name='محصول تست', category=cls.category, publish_status=Product.PublishStatus.PUBLISHED)

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_dashboard_and_critical_forms_render_without_losing_native_controls(self):
        for name in ('index', 'main_flower_changelist', 'main_samedayflower_add', 'main_weddingproduct_add', 'main_bakeryitem_add', 'main_giftitem_add', 'main_pagecontentblock_add', 'main_workshoppagecontent_add', 'main_newspost_add', 'main_story_add', 'main_sitehero_add'):
            with self.subTest(name=name):
                response = self.client.get(reverse(f'admin:{name}'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'admin_modern.css')
                self.assertContains(response, 'zad-sidebar')
                if name.endswith('_add'):
                    self.assertContains(response, 'csrfmiddlewaretoken')
                    self.assertContains(response, 'name="_save"')
        response = self.client.get(reverse('admin:main_flower_change', args=[self.product.pk]))
        self.assertContains(response, 'محل نمایش در سایت')
        self.assertContains(response, self.product.get_absolute_url())
        self.assertContains(response, 'name="_continue"')

    def test_staff_navigation_and_add_buttons_follow_model_permissions(self):
        ct = ContentType.objects.get_for_model(Story)
        self.staff.user_permissions.add(Permission.objects.get(content_type=ct, codename='view_story'))
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('admin:main_story_changelist'))
        self.assertNotContains(response, reverse('admin:main_story_add'))
        self.assertNotContains(response, reverse('admin:main_flower_changelist'))
        self.assertNotContains(response, reverse('admin:auth_user_changelist'))
        self.assertEqual(self.client.get(reverse('admin:main_pagecontentblock_add')).status_code, 403)

    def test_view_only_product_form_has_no_save_or_delete_controls(self):
        ct = ContentType.objects.get_for_model(Flower, for_concrete_model=False)
        self.staff.user_permissions.add(Permission.objects.get(content_type=ct, codename='view_flower'))
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin:main_flower_change', args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="_save"')
        self.assertNotContains(response, reverse('admin:main_flower_delete', args=[self.product.pk]))

    def test_exposed_content_models_appear_in_dashboard(self):
        response = self.client.get(reverse('admin:index'))
        for name in ('pagecontentblock', 'workshoppagecontent', 'newspost'):
            self.assertContains(response, reverse(f'admin:main_{name}_changelist'))
        self.assertNotContains(response, reverse('admin:main_productimage_changelist'))

    def test_admin_saved_contact_copy_reaches_public_page_and_inactive_restores_default(self):
        data = {'page': 'contact', 'section_key': 'intro', 'kicker': 'TEST', 'title': 'عنوان اختصاصی از پنل', 'body': 'متن اختصاصی از پنل', 'is_active': 'on', 'sort_order': 0, '_save': 'ذخیره'}
        response = self.client.post(reverse('admin:main_pagecontentblock_add'), data)
        self.assertEqual(response.status_code, 302)
        block = PageContentBlock.objects.get(page='contact', section_key='intro')
        self.assertContains(self.client.get(reverse('contact')), data['title'])
        block.is_active = False
        block.save()
        self.assertNotContains(self.client.get(reverse('contact')), data['title'])

    def test_new_invalid_slot_is_rejected_but_existing_legacy_values_are_preserved(self):
        values = {'page': 'faq', 'section_key': 'story', 'sort_order': 0, 'title': 'title', 'is_active': True}
        form = PageContentBlockAdminForm(data=values)
        self.assertFalse(form.is_valid())
        self.assertIn('section_key', form.errors)
        legacy = PageContentBlock.objects.create(page='home', section_key='legacy', cta_text='متن قبلی', cta_url='/contact/')
        values.update(page='home', section_key='legacy', cta_text=legacy.cta_text, cta_url=legacy.cta_url)
        form = PageContentBlockAdminForm(data=values, instance=legacy)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        legacy.refresh_from_db()
        self.assertEqual(legacy.cta_text, 'متن قبلی')

    def test_login_keeps_authentication_and_accessible_fields(self):
        self.client.logout()
        response = self.client.get(reverse('admin:login'))
        self.assertContains(response, 'label for="id_username"')
        self.assertContains(response, 'label for="id_password"')
        self.assertContains(response, 'csrfmiddlewaretoken')
        response = self.client.post(reverse('admin:login'), {'username': 'workspace-admin', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="alert"')
        response = self.client.post(reverse('admin:login'), {'username': 'workspace-admin', 'password': 'test-password', 'next': reverse('admin:index')})
        self.assertRedirects(response, reverse('admin:index'))

    def test_product_delete_still_uses_django_confirmation(self):
        response = self.client.get(reverse('admin:main_flower_delete', args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.assertContains(response, 'csrfmiddlewaretoken')
