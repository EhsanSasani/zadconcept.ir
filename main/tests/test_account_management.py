import json

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from main.account_roles import account_version, assigned_roles
from main.account_forms import AccountForm
from main.account_service import save_account
from main.models import Florist, StudioProduct


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AccountManagementTests(TestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user('manager', first_name='مدیر', password='Test-manager-928!')
        self.manager.user_permissions.add(*Permission.objects.filter(codename__in=[
            'view_studioproduct', 'manage_studio_accounts']))
        self.user = get_user_model().objects.create_user('colleague', first_name='همکار', password='Original-837!')
        self.client.force_login(self.manager)

    def payload(self, **changes):
        data = {'username': 'new-colleague', 'first_name': 'متین', 'last_name': 'زاد',
                'email': '', 'roles': ['sales'], 'is_active': 'on',
                'password1': 'A-new-private-pass-634!', 'password2': 'A-new-private-pass-634!'}
        data.update(changes)
        return data

    def edit(self, user=None, **changes):
        user = user or self.user
        fresh = get_user_model().objects.get(pk=user.pk)
        data = self.payload(username=fresh.username, first_name=fresh.first_name,
                            version=account_version(fresh), password1='', password2='')
        data.update(changes)
        return self.client.post(reverse('studio_account_edit', args=[user.pk]), data)

    def test_create_all_three_roles_without_staff_or_admin_access(self):
        response = self.client.post(reverse('studio_account_add'), self.payload(
            roles=['manager', 'sales', 'florist'], is_staff='on', is_superuser='on'))
        self.assertRedirects(response, reverse('studio_accounts'))
        user = get_user_model().objects.get(username='new-colleague')
        self.assertEqual(assigned_roles(user), ['manager', 'sales', 'florist'])
        self.assertTrue(user.has_perm('main.manage_studio_accounts'))
        self.assertTrue(user.has_perm('main.change_studioproduct'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_perm('auth.change_user'))
        self.assertEqual(Florist.objects.get(user=user).name, 'متین زاد')

    def test_sales_only_account_needs_no_florist(self):
        response = self.client.post(reverse('studio_account_add'), self.payload())
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='new-colleague')
        self.assertFalse(Florist.objects.filter(user=user).exists())
        client = Client()
        response = client.post('/studio/login/', {'username': user.username, 'password': 'A-new-private-pass-634!'})
        self.assertRedirects(response, '/sales/')

    def test_edit_direct_and_group_permissions_revokes_live_session(self):
        group = Group.objects.create(name='Studio sales')
        group.permissions.add(Permission.objects.get(codename='use_sales_workspace'))
        self.user.groups.add(group)
        self.user.user_permissions.add(Permission.objects.get(codename='use_sales_workspace'))
        other = Client()
        other.force_login(self.user)
        self.assertEqual(other.get('/sales/').status_code, 200)
        self.assertEqual(self.edit(roles=['florist']).status_code, 302)
        fresh = get_user_model().objects.get(pk=self.user.pk)
        self.assertEqual(assigned_roles(fresh), ['florist'])
        self.assertFalse(fresh.has_perm('main.use_sales_workspace'))
        self.assertRedirects(other.get('/sales/'), '/panel/', fetch_redirect_response=False)
        self.assertEqual(other.get('/team/').status_code, 200)

    def test_revoking_florist_preserves_profile_and_production_history(self):
        florist = Florist.objects.create(name='همکار', code='history', user=self.user)
        product = StudioProduct.objects.create(factor_code='H-1', florist=florist, product_type='box',
            production_type='CUSTOM', price=1000, image='example.webp', source='PORTAL', created_by=self.user)
        self.assertEqual(self.edit(roles=['sales']).status_code, 302)
        florist.refresh_from_db()
        product.refresh_from_db()
        self.assertIsNone(florist.user_id)
        self.assertEqual(product.florist_id, florist.pk)
        self.assertEqual(self.edit(roles=['sales', 'florist'], florist=florist.pk).status_code, 302)
        self.assertEqual(Florist.objects.get(user=self.user).pk, florist.pk)

    def test_existing_florist_cannot_be_taken_from_another_account(self):
        florist = Florist.objects.create(name='مدیر', code='taken', user=self.manager)
        response = self.edit(roles=['florist'], florist=florist.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn('florist', response.context['form'].errors)
        florist.refresh_from_db()
        self.assertEqual(florist.user_id, self.manager.pk)

    def test_stale_form_cannot_overwrite_new_role_change(self):
        stale = account_version(self.user)
        self.assertEqual(self.edit(roles=['sales']).status_code, 302)
        response = self.edit(roles=['manager'], version=stale)
        self.assertContains(response, 'این حساب در صفحهٔ دیگری تغییر کرده است')
        self.assertEqual(assigned_roles(get_user_model().objects.get(pk=self.user.pk)), ['sales'])

    def test_editable_manager_can_be_updated_but_not_self_locked_out(self):
        self.user.user_permissions.add(Permission.objects.get(codename='view_studioproduct'))
        self.assertEqual(self.edit(roles=['manager', 'sales']).status_code, 302)
        self.assertEqual(assigned_roles(get_user_model().objects.get(pk=self.user.pk)), ['manager', 'sales'])
        for values in ({'roles': ['sales']}, {'roles': ['manager'], 'is_active': ''}):
            self.assertContains(self.edit(self.manager, **values), 'نمی‌توانید ورود یا دسترسی مدیریت')
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_technical_accounts_are_protected_from_takeover(self):
        for flags in ({'is_staff': True}, {'is_superuser': True}):
            self.user.is_staff = flags.get('is_staff', False)
            self.user.is_superuser = flags.get('is_superuser', False)
            self.user.save()
            self.assertEqual(self.edit().status_code, 403)
        self.user.is_superuser = False
        self.user.save()
        self.user.user_permissions.add(Permission.objects.get(codename='change_user'))
        self.assertEqual(self.edit().status_code, 403)

    def test_blank_password_preserves_and_reset_invalidates_other_sessions(self):
        old_hash = self.user.password
        other = Client()
        other.force_login(self.user)
        self.edit(roles=['sales'])
        self.user.refresh_from_db()
        self.assertEqual(old_hash, self.user.password)
        self.assertEqual(other.get('/sales/').status_code, 200)
        response = self.edit(password1='Changed-private-848!', password2='Changed-private-848!')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(other.get('/sales/').status_code, 302)
        audit = json.loads(LogEntry.objects.latest('id').change_message)
        self.assertTrue(audit['password_changed'])
        self.assertNotIn('Changed-private', json.dumps(audit))

    def test_disabled_account_loses_session_access_without_deletion(self):
        self.edit(roles=['florist'])
        other = Client()
        other.force_login(self.user)
        self.assertEqual(other.get('/team/').status_code, 200)
        self.assertEqual(self.edit(is_active='', roles=['florist']).status_code, 302)
        self.assertEqual(other.get('/team/').status_code, 302)
        self.assertTrue(Florist.objects.filter(user=self.user).exists())

    def test_nonmanager_cannot_manage_users_and_csrf_is_enforced(self):
        client = Client()
        client.force_login(self.user)
        for url in ['/studio/accounts/', '/studio/accounts/new/', f'/studio/accounts/{self.manager.pk}/']:
            self.assertEqual(client.get(url).status_code, 403)
            self.assertEqual(client.post(url, self.payload()).status_code, 403)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.manager)
        self.assertEqual(strict.post('/studio/accounts/new/', self.payload()).status_code, 403)

    def test_role_and_username_validation_and_audit(self):
        for changes, field in [({'roles': []}, 'roles'), ({'roles': ['admin']}, 'roles'),
                               ({'username': 'MANAGER'}, 'username'),
                               ({'password2': 'mismatch'}, 'password2')]:
            response = self.client.post('/studio/accounts/new/', self.payload(**changes))
            self.assertEqual(response.status_code, 200)
            self.assertIn(field, response.context['form'].errors)
        self.assertEqual(self.edit(first_name='بهناز', email='sales@example.com').status_code, 302)
        audit = json.loads(LogEntry.objects.latest('id').change_message)
        self.assertEqual(audit['after']['first_name'], 'بهناز')
        self.assertEqual(LogEntry.objects.latest('id').user_id, self.manager.pk)

    def test_list_includes_unlinked_users_and_search(self):
        response = self.client.get('/studio/accounts/')
        self.assertContains(response, self.user.username)
        self.assertContains(response, 'مدیریت کاربران')
        self.assertIn('no-store', response['Cache-Control'])
        response = self.client.get('/studio/accounts/', {'q': 'colleague'})
        self.assertEqual(response.context['page'].paginator.count, 1)

    def test_profile_deleted_after_validation_rolls_back_new_account(self):
        florist = Florist.objects.create(name='همکار', code='disappearing')
        form = AccountForm(self.payload(roles=['florist'], florist=florist.pk))
        self.assertTrue(form.is_valid(), form.errors)
        Florist.objects.filter(pk=florist.pk).delete()
        with self.assertRaises(ValidationError):
            save_account(actor=self.manager, data=form.cleaned_data)
        self.assertFalse(get_user_model().objects.filter(username='new-colleague').exists())
        self.assertFalse(LogEntry.objects.exists())

    def test_manager_permission_rechecked_at_write_time(self):
        self.assertTrue(self.manager.has_perm('main.manage_studio_accounts'))
        form = AccountForm(self.payload())
        self.assertTrue(form.is_valid())
        self.manager.user_permissions.clear()
        with self.assertRaises(PermissionDenied):
            save_account(actor=self.manager, data=form.cleaned_data)
        self.assertFalse(get_user_model().objects.filter(username='new-colleague').exists())
