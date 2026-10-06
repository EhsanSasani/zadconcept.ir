from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from main.models import Florist
from main.panel import SESSION_KEY


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PanelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('panel-user', password='test-panel-password')

    def grant(self, *permissions):
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='main', codename__in=permissions))

    def florist(self):
        return Florist.objects.create(user=self.user, name='آزمایش', code='panel-test')

    def login(self):
        self.client.force_login(self.user)

    def test_anonymous_entry_returns_to_panel_after_login(self):
        response = self.client.get('/panel/')
        self.assertRedirects(response, '/studio/login/?next=/panel/', fetch_redirect_response=False)

    def test_single_role_goes_directly_to_workspace_and_has_no_switcher(self):
        for permission, destination in [('use_sales_workspace', '/sales/'), ('view_studioproduct', '/studio/')]:
            self.user.user_permissions.clear()
            self.grant(permission)
            self.login()
            response = self.client.get('/panel/', follow=True)
            self.assertEqual(response.redirect_chain, [(destination, 302)])
            self.assertNotContains(response, 'تغییر فضای کاری')

    def test_single_florist_and_disabled_profile(self):
        florist = self.florist()
        self.login()
        self.assertRedirects(self.client.get('/panel/'), '/team/')
        florist.is_active = False
        florist.save(update_fields=['is_active'])
        self.assertContains(self.client.get('/panel/'), 'هنوز فضای کاری فعالی')

    def test_multiple_roles_choose_instead_of_florist_priority(self):
        self.florist()
        self.grant('view_studioproduct', 'use_sales_workspace')
        response = self.client.post('/studio/login/', {'username': self.user.username,
            'password': 'test-panel-password'}, follow=True)
        self.assertEqual(response.redirect_chain, [('/panel/', 302)])
        self.assertEqual([item['key'] for item in response.context['choices']], ['studio', 'sales', 'team'])

    def test_previous_selection_is_highlighted_but_multi_role_always_chooses(self):
        self.grant('view_studioproduct', 'use_sales_workspace')
        self.login()
        self.assertRedirects(self.client.post('/panel/select/', {'workspace': 'sales'}), '/sales/')
        self.assertEqual(self.client.session[SESSION_KEY], 'sales')
        self.assertEqual(self.client.get('/panel/').status_code, 200)
        self.assertContains(self.client.get('/panel/?choose=1'), 'آخرین فضای انتخاب‌شده')
        self.assertRedirects(self.client.post('/panel/select/', {'workspace': 'studio'}), '/studio/')
        self.assertRedirects(self.client.get('/studio/login/'), '/panel/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/panel/').status_code, 200)

    def test_revoked_selection_is_discarded(self):
        self.grant('view_studioproduct', 'use_sales_workspace')
        self.login()
        self.client.post('/panel/select/', {'workspace': 'sales'})
        self.user.user_permissions.remove(Permission.objects.get(codename='use_sales_workspace'))
        self.assertRedirects(self.client.get('/panel/'), '/studio/')
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.client.post('/panel/select/', {'workspace': 'sales'}).status_code, 403)

    def test_unavailable_workspace_and_external_target_never_grant_access(self):
        self.grant('use_sales_workspace')
        self.login()
        for key in ['studio', 'team', 'https://example.com', '../admin', '']:
            response = self.client.post('/panel/select/', {'workspace': key})
            self.assertContains(response, 'به این بخش دسترسی ندارید.', status_code=403)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertFalse(self.user.is_staff)

    def test_selection_requires_post_and_csrf(self):
        self.grant('use_sales_workspace')
        self.login()
        self.assertEqual(self.client.get('/panel/select/').status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post('/panel/select/', {'workspace': 'sales'}).status_code, 403)
        self.assertNotIn(SESSION_KEY, client.session)

    def test_workspace_denials_are_useful_and_remain_403(self):
        self.grant('use_sales_workspace')
        self.login()
        for url in ['/studio/accounts/']:
            response = self.client.get(url)
            self.assertContains(response, 'رفتن به پنل من', status_code=403)
            self.assertIn('no-store', response['Cache-Control'])
        response = self.client.get('/studio/', HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['panel_url'], '/panel/')

    def test_three_workspaces_show_consistent_switcher(self):
        self.florist()
        self.grant('view_studioproduct', 'use_sales_workspace')
        self.login()
        for url in ['/studio/', '/sales/', '/team/']:
            response = self.client.get(url)
            self.assertContains(response, 'تغییر فضای کاری')
            self.assertContains(response, '/panel/?choose=1')
            self.assertIn('no-store', response['Cache-Control'])

    def test_logout_clears_choice_and_does_not_leak_it_to_next_account(self):
        self.grant('use_sales_workspace')
        self.login()
        self.client.post('/panel/select/', {'workspace': 'sales'})
        self.client.post('/studio/logout/')
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_no_roles_and_inactive_user_cannot_select(self):
        self.login()
        self.assertContains(self.client.get('/panel/'), 'هنوز فضای کاری فعالی')
        self.assertEqual(self.client.post('/panel/select/', {'workspace': 'studio'}).status_code, 403)
        self.grant('use_sales_workspace')
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertRedirects(self.client.get('/panel/'), '/studio/login/?next=/panel/', fetch_redirect_response=False)

    def test_multi_role_login_chooses_even_with_old_bookmark_next(self):
        self.florist()
        self.grant('use_sales_workspace')
        response = self.client.post('/studio/login/', {'username': self.user.username,
            'password': 'test-panel-password', 'next': '/team/products/?status=SOLD'})
        self.assertRedirects(response, '/panel/')

    def test_revoked_workspace_bookmark_returns_to_panel_without_logout(self):
        self.grant('use_sales_workspace')
        self.login()
        for path in ['/studio/', '/team/']:
            response = self.client.get(path, follow=True)
            self.assertEqual(response.redirect_chain, [('/panel/', 302), ('/sales/', 302)])
            self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.assertEqual(self.client.post('/panel/select/', {'workspace': 'studio'}).status_code, 403)

    def test_panel_chooser_is_private(self):
        self.grant('use_sales_workspace')
        self.login()
        response = self.client.get('/panel/?choose=1')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertContains(response, 'noindex,nofollow')

    def test_existing_app_shortcut_uses_shared_entry_and_preserves_identity(self):
        response = self.client.get(reverse('team_manifest'))
        self.assertEqual(response.json()['start_url'], '/panel/')
        self.assertEqual(response.json()['id'], '/team/')
