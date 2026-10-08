"""HTTP boundaries and localized entry flows for purchase and waste records."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from itertools import count
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from main.account_roles import account_version, assigned_roles, editable_account
from main.account_service import save_account
from main.models import Florist, Material, ProcurementAudit, PurchaseInvoice, WasteEntry
from main.panel import SESSION_KEY
from main.procurement_forms import JalaliDayField, PersianDecimalField, PurchaseLineFormSet
from main.procurement_service import create_purchase, create_waste, record_version, save_material, void_purchase


class ProcurementLocalizedInputTests(SimpleTestCase):
    def test_whole_toman_amounts_accept_persian_and_conventional_grouping(self):
        field = PersianDecimalField(money=True, max_digits=15, decimal_places=0, min_value=0)
        for value in ('۲.۳۰۰.۰۰۰', '٢٬٣٠٠٬٠٠٠', '2,300,000', '۲۳۰۰۰۰۰'):
            with self.subTest(value=value):
                self.assertEqual(field.clean(value), Decimal('2300000'))
        for value in ('-1', '+2', '1e3', 'NaN', 'Infinity', '1.5', '1.00.000'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                field.clean(value)

    def test_fractional_quantities_are_not_treated_as_money_groups(self):
        field = PersianDecimalField(max_digits=12, decimal_places=3, min_value=Decimal('0.001'))
        self.assertEqual(field.clean('۱٫۵'), Decimal('1.5'))
        self.assertEqual(field.clean('۱.۰۰۰'), Decimal('1'))
        for value in ('0', '0.0001', '2.300.000'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                field.clean(value)

    def test_jalali_input_accepts_persian_digits_and_rejects_invalid_or_future_days(self):
        with patch('django.utils.timezone.localdate', return_value=date(2026, 10, 7)):
            field = JalaliDayField()
            for value in ('۱۴۰۵/۰۷/۱۵', '1405.7.15', '۱۴۰۵-۷-۱۵'):
                self.assertEqual(field.clean(value), date(2026, 10, 7))
            for value in ('۱۴۰۴/۱۲/۳۰', '۱۴۰۵/۰۷/۱۶', '2026/10/07', ''):
                with self.subTest(value=value), self.assertRaises(ValidationError):
                    field.clean(value)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ProcurementViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.buyer = users.objects.create_user('procurement-buyer', password='procurement-test-password')
        cls.second_buyer = users.objects.create_user('procurement-other')
        cls.manager = users.objects.create_user('procurement-manager')
        cls.seller = users.objects.create_user('procurement-seller')
        cls.florist_user = users.objects.create_user('procurement-florist')
        cls.permission = Permission.objects.get(content_type__app_label='main', codename='use_procurement_workspace')
        cls.buyer.user_permissions.add(cls.permission)
        cls.second_buyer.user_permissions.add(cls.permission)
        cls.manager.user_permissions.add(Permission.objects.get(content_type__app_label='main', codename='view_studioproduct'))
        cls.seller.user_permissions.add(Permission.objects.get(content_type__app_label='main', codename='use_sales_workspace'))
        Florist.objects.create(user=cls.florist_user, name='فلوریست آزمایشی', code='procurement-florist')
        cls.material = Material.objects.create(name='رز', base_unit='شاخه', purchase_unit='بسته',
            units_per_purchase=10, default_unit_price=100000)

    def setUp(self):
        ticks = count()
        self.clock = patch('django.utils.timezone.now',
            side_effect=lambda: datetime(2026, 10, 7, 9, 30, tzinfo=ZoneInfo('UTC'))
                + timedelta(microseconds=next(ticks)))
        self.clock.start()
        self.addCleanup(self.clock.stop)
        Material.objects.filter(pk=self.material.pk).update(updated_at=timezone.now())
        self.material.refresh_from_db()
        self.client.force_login(self.buyer)

    def entry_data(self, kind='purchase', **changes):
        response = self.client.get(reverse(f'procurement_{kind}_add'))
        self.assertEqual(response.status_code, 200)
        data = {
            'token': response.context['form']['token'].value(), 'date': '۱۴۰۵/۰۷/۱۵',
            'lines-TOTAL_FORMS': '1', 'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '0', 'lines-MAX_NUM_FORMS': '50',
            'lines-0-material': str(self.material.pk), 'lines-0-unit_mode': 'purchase',
            'lines-0-quantity': '۲', 'lines-0-conversion_factor': '۲۰',
        }
        if kind == 'purchase':
            data.update(supplier='بازار گل', reference='P-01', notes='خرید روزانه', **{'lines-0-unit_price': '۲.۳۰۰.۰۰۰'})
        else:
            data.update(reason='wilted', notes='دورریز روزانه', **{'lines-0-unit_mode': 'base', 'lines-0-quantity': '۳'})
        data.update(changes)
        return data

    def service_purchase(self, day=date(2026, 10, 7), price=100000):
        return create_purchase(actor=self.buyer, data={'date': day, 'supplier': 'بازار گل'},
            lines=[{'material': self.material, 'unit_mode': 'purchase', 'quantity': 1,
                    'conversion_factor': 10, 'unit_price': price}], submission_key=uuid4())[0]

    def service_waste(self, day=date(2026, 10, 7)):
        return create_waste(actor=self.buyer, data={'date': day, 'reason': 'wilted'},
            lines=[{'material': self.material, 'unit_mode': 'base', 'quantity': 2}], submission_key=uuid4())[0]

    def test_new_role_is_independent_and_single_role_login_opens_workspace(self):
        self.assertEqual(assigned_roles(self.buyer), ['procurement'])
        self.assertTrue(editable_account(self.buyer))
        self.assertFalse(self.buyer.is_staff)
        self.assertRedirects(self.client.get(reverse('panel_home')), reverse('procurement_home'))
        self.client.logout()
        response = self.client.post(reverse('studio_login'),
            {'username': self.buyer.username, 'password': 'procurement-test-password'})
        self.assertRedirects(response, reverse('procurement_home'))
        self.assertEqual(self.client.get(reverse('studio_procurement')).status_code, 403)
        self.assertEqual(self.client.get(reverse('sales_history')).status_code, 403)

    def test_manager_grants_and_revokes_procurement_without_other_privileges(self):
        self.manager.user_permissions.add(Permission.objects.get(codename='manage_studio_accounts'))
        target = get_user_model().objects.create_user('new-procurement-user', password='existing-test-password')

        def save_roles(roles):
            current = get_user_model().objects.get(pk=target.pk)
            return save_account(actor=self.manager, user_id=target.pk, data={
                'version': account_version(current), 'username': current.username,
                'first_name': 'کاربر', 'last_name': 'آزمایشی', 'email': '', 'is_active': True,
                'roles': roles, 'password1': '', 'florist': None})

        save_roles(['procurement'])
        fresh = get_user_model().objects.get(pk=target.pk)
        self.assertEqual(assigned_roles(fresh), ['procurement'])
        self.assertEqual(fresh.get_all_permissions(), {'main.use_procurement_workspace'})
        self.assertFalse(fresh.is_staff)
        self.assertFalse(fresh.is_superuser)
        self.assertTrue(fresh.check_password('existing-test-password'))
        self.assertFalse(Florist.objects.filter(user=fresh).exists())
        self.client.force_login(fresh)
        self.assertRedirects(self.client.get(reverse('panel_home')), reverse('procurement_home'))

        save_roles(['sales', 'procurement'])
        save_roles(['sales'])
        fresh = get_user_model().objects.get(pk=target.pk)
        self.assertEqual(assigned_roles(fresh), ['sales'])
        self.assertEqual(fresh.get_all_permissions(), {'main.use_sales_workspace'})
        self.assertEqual(self.client.get(reverse('procurement_purchase_add')).status_code, 403)
        self.assertEqual(self.client.get(reverse('sales_home')).status_code, 200)

    def test_procurement_role_cannot_grant_itself_account_management(self):
        with self.assertRaises(PermissionDenied):
            save_account(actor=self.buyer, user_id=self.buyer.pk, data={
                'version': account_version(self.buyer), 'username': self.buyer.username,
                'first_name': '', 'last_name': '', 'email': '', 'is_active': True,
                'roles': ['manager', 'procurement'], 'password1': '', 'florist': None})
        self.assertEqual(assigned_roles(get_user_model().objects.get(pk=self.buyer.pk)), ['procurement'])

    def test_procurement_bootstrap_command_preserves_existing_password_and_grants_only_its_role(self):
        user = get_user_model().objects.create_user('procurement-command', password='existing-command-password')
        original_password = user.password
        output = StringIO()
        with patch('main.management.commands.studio_account.getpass') as prompt:
            call_command('studio_account', user.username, procurement=True, stdout=output)
            call_command('studio_account', user.username, procurement=True, stdout=output)
        prompt.assert_not_called()
        user.refresh_from_db()
        self.assertEqual(user.password, original_password)
        self.assertTrue(user.check_password('existing-command-password'))
        self.assertEqual(user.get_all_permissions(), {'main.use_procurement_workspace'})
        self.assertEqual(assigned_roles(user), ['procurement'])
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertIn('Existing password preserved', output.getvalue())

    def test_live_material_options_are_private_get_only_and_exclude_inactive_items(self):
        url = reverse('procurement_material_options')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        items = response.json()['materials']
        self.assertEqual([item['id'] for item in items], [self.material.pk])
        self.assertEqual(items[0]['name'], 'رز')
        self.assertEqual(Decimal(items[0]['units_per_purchase']), Decimal('10'))
        self.assertEqual(Decimal(items[0]['default_unit_price']), Decimal('100000'))

        Material.objects.filter(pk=self.material.pk).update(is_active=False)
        replacement = Material.objects.create(name='لیلیوم', base_unit='شاخه', purchase_unit='بسته',
            units_per_purchase=5, default_unit_price=450000)
        self.assertEqual([item['id'] for item in self.client.get(url).json()['materials']], [replacement.pk])
        self.assertEqual(self.client.post(url, {}).status_code, 405)
        for user in (self.manager, self.seller, self.florist_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                denied = self.client.get(url, HTTP_ACCEPT='application/json')
                self.assertEqual(denied.status_code, 403)
                self.assertNotIn('materials', denied.json())
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_multi_role_chooser_lists_procurement_and_rechecks_revoked_selection(self):
        self.buyer.user_permissions.add(Permission.objects.get(codename='use_sales_workspace'))
        response = self.client.get(reverse('panel_home'))
        self.assertEqual([row['key'] for row in response.context['choices']], ['sales', 'procurement'])
        self.assertRedirects(self.client.post(reverse('panel_select'), {'workspace': 'procurement'}),
            reverse('procurement_home'))
        self.assertEqual(self.client.session[SESSION_KEY], 'procurement')
        self.buyer.user_permissions.remove(self.permission)
        response = self.client.get(reverse('procurement_home'), follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('panel_home'), 302), (reverse('sales_home'), 302)])
        self.assertEqual(int(self.client.session['_auth_user_id']), self.buyer.pk)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(self.client.post(reverse('panel_select'), {'workspace': 'procurement'}).status_code, 403)

    def test_anonymous_and_other_operational_roles_cannot_read_or_write_ledgers(self):
        invoice = self.service_purchase()
        self.client.logout()
        response = self.client.get(reverse('procurement_home'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('studio_login')))
        for user in (self.seller, self.florist_user):
            self.client.force_login(user)
            for name, args in [('procurement_purchases', []), ('procurement_wastes', []),
                ('procurement_purchase_detail', [invoice.pk]), ('procurement_materials', []),
                ('procurement_purchase_add', []), ('procurement_waste_add', []), ('studio_procurement', [])]:
                with self.subTest(user=user.username, name=name):
                    self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)
            self.assertEqual(self.client.post(reverse('procurement_purchase_add'), {}).status_code, 403)

    def test_manager_can_monitor_but_cannot_create_edit_or_void(self):
        invoice = self.service_purchase()
        waste = self.service_waste()
        self.client.force_login(self.manager)
        for name, args in [('studio_procurement', []), ('procurement_purchases', []),
            ('procurement_wastes', []), ('procurement_purchase_detail', [invoice.pk]),
            ('procurement_waste_detail', [waste.pk])]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 200)
                if name != 'studio_procurement':
                    self.assertFalse(response.context['can_write'])
                    self.assertNotContains(response, 'action="' + reverse('procurement_purchase_void', args=[invoice.pk]) + '"')
        for name, args in [('procurement_material_add', []), ('procurement_material_edit', [self.material.pk]),
            ('procurement_purchase_add', []), ('procurement_waste_add', []),
            ('procurement_purchase_void', [invoice.pk]), ('procurement_waste_void', [waste.pk])]:
            with self.subTest(name=name):
                self.assertEqual(self.client.post(reverse(name, args=args), {}).status_code, 403)
        self.assertEqual(PurchaseInvoice.objects.count(), 1)
        self.assertEqual(WasteEntry.objects.count(), 1)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'ACTIVE')

    def test_purchase_localized_amount_and_variable_pack_are_saved_once(self):
        data = self.entry_data()
        first = self.client.post(reverse('procurement_purchase_add'), data)
        self.assertEqual(first.status_code, 302)
        invoice = PurchaseInvoice.objects.get()
        self.assertEqual(invoice.date, date(2026, 10, 7))
        self.assertEqual(invoice.total_amount, Decimal('4600000'))
        row = invoice.lines.get()
        self.assertEqual(row.base_quantity, 40)
        self.assertEqual(row.conversion_factor, 20)
        self.assertEqual(row.unit_label, 'بسته')
        self.assertEqual(invoice.created_by_id, self.buyer.pk)
        duplicate = self.client.post(reverse('procurement_purchase_add'), data)
        self.assertEqual(duplicate.url, first.url)
        self.assertEqual(PurchaseInvoice.objects.count(), 1)
        self.assertEqual(ProcurementAudit.objects.filter(target_type='purchaseinvoice', action='create').count(), 1)
        response = self.client.get(first.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'بازار گل')

    def test_save_and_another_starts_a_fresh_token(self):
        data = self.entry_data(submit='another')
        response = self.client.post(reverse('procurement_purchase_add'), data)
        self.assertRedirects(response, reverse('procurement_purchase_add'))
        next_form = self.client.get(reverse('procurement_purchase_add')).context['form']
        self.assertNotEqual(next_form['token'].value(), data['token'])
        self.assertEqual(PurchaseInvoice.objects.count(), 1)

    def test_tokens_cannot_be_forged_shared_between_actors_or_reused_for_other_kind(self):
        data = self.entry_data()
        response = self.client.post(reverse('procurement_purchase_add'), {**data, 'token': 'forged'})
        self.assertEqual(response.status_code, 400)
        self.client.force_login(self.second_buyer)
        self.assertEqual(self.client.post(reverse('procurement_purchase_add'), data).status_code, 400)
        self.client.force_login(self.buyer)
        waste_data = self.entry_data('waste', token=data['token'])
        self.assertEqual(self.client.post(reverse('procurement_waste_add'), waste_data).status_code, 400)
        self.assertFalse(PurchaseInvoice.objects.exists())
        self.assertFalse(WasteEntry.objects.exists())

    def test_invalid_header_line_and_empty_formset_never_create_partial_records(self):
        for changes in ({'date': '۱۴۰۵/۰۷/۱۶'}, {'date': '۱۴۰۴/۱۲/۳۰'},
            {'lines-0-quantity': '0'}, {'lines-0-conversion_factor': '-1'},
            {'lines-0-unit_price': '1.5'}, {'lines-0-material': '999999'},
            {'lines-TOTAL_FORMS': '0'}, {'lines-0-DELETE': 'on'}, {'lines-TOTAL_FORMS': '51'}):
            with self.subTest(changes=changes):
                response = self.client.post(reverse('procurement_purchase_add'), self.entry_data(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.context['form'].errors or response.context['formset'].errors
                    or response.context['formset'].non_form_errors())
        self.assertFalse(PurchaseInvoice.objects.exists())
        self.assertFalse(ProcurementAudit.objects.exists())

    def test_unused_blank_rows_are_ignored_and_deleted_rows_are_not_saved(self):
        data = self.entry_data(**{'lines-TOTAL_FORMS': '3', 'lines-1-unit_mode': 'purchase',
            'lines-2-unit_mode': 'purchase', 'lines-2-material': str(self.material.pk),
            'lines-2-quantity': '0', 'lines-2-unit_price': 'invalid', 'lines-2-DELETE': 'on'})
        response = self.client.post(reverse('procurement_purchase_add'), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PurchaseInvoice.objects.get().lines.count(), 1)

    def test_archived_material_is_rejected_even_if_selected_on_an_open_form(self):
        data = self.entry_data()
        Material.objects.filter(pk=self.material.pk).update(is_active=False)
        response = self.client.post(reverse('procurement_purchase_add'), data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('material', response.context['formset'].forms[0].errors)
        self.assertFalse(PurchaseInvoice.objects.exists())

    def test_changed_catalog_rejects_no_js_submission_until_current_selection_is_acknowledged(self):
        for kind, model in [('purchase', PurchaseInvoice), ('waste', WasteEntry)]:
            with self.subTest(kind=kind):
                data = self.entry_data(kind)
                self.assertNotIn('lines-0-material_version', data)
                self.material.refresh_from_db()
                save_material(actor=self.buyer, pk=self.material.pk,
                    expected_version=record_version(self.material), data={
                        'name': 'رز هلندی', 'base_unit': 'شاخه', 'purchase_unit': 'بسته',
                        'units_per_purchase': 25, 'default_unit_price': 500000, 'is_active': True})
                rejected = self.client.post(reverse(f'procurement_{kind}_add'), data)
                self.assertEqual(rejected.status_code, 400)
                self.assertTrue(rejected.context['form'].non_field_errors())
                self.assertContains(rejected, 'تغییر کرده است', status_code=400)
                self.assertFalse(model.objects.exists())

                options = self.client.get(reverse('procurement_material_options')).json()['materials']
                current = next(row for row in options if row['id'] == self.material.pk)
                # An explicit refreshed selection can reuse the original header token.
                response = self.client.post(reverse(f'procurement_{kind}_add'), {
                    **data, 'lines-0-material_version': current['version']})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(model.objects.count(), 1)
                self.assertEqual(model.objects.get().lines.get().material_name, 'رز هلندی')

    def test_stale_hidden_material_version_rejects_even_with_a_newer_form_token(self):
        old_version = self.client.get(reverse('procurement_material_options')).json()['materials'][0]['version']
        save_material(actor=self.buyer, pk=self.material.pk,
            expected_version=record_version(self.material), data={
                'name': 'رز', 'base_unit': 'شاخه', 'purchase_unit': 'دسته',
                'units_per_purchase': 20, 'default_unit_price': 300000, 'is_active': True})
        for kind in ('purchase', 'waste'):
            with self.subTest(kind=kind):
                data = self.entry_data(kind, **{'lines-0-material_version': old_version})
                response = self.client.post(reverse(f'procurement_{kind}_add'), data)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, 'تغییر کرده است', status_code=400)
        self.assertFalse(PurchaseInvoice.objects.exists())
        self.assertFalse(WasteEntry.objects.exists())

    def test_waste_uses_server_cost_and_backdated_purchase_basis(self):
        self.service_purchase(day=date(2026, 10, 5), price=120000)
        self.service_purchase(day=date(2026, 10, 7), price=500000)
        data = self.entry_data('waste', date='۱۴۰۵/۰۷/۱۴', **{'lines-0-unit_price': '999999999', 'estimated_total': '1'})
        response = self.client.post(reverse('procurement_waste_add'), data)
        self.assertEqual(response.status_code, 302)
        entry = WasteEntry.objects.get()
        self.assertEqual(entry.date, date(2026, 10, 6))
        self.assertEqual(entry.estimated_total, 36000)
        self.assertEqual(entry.lines.get().unit_cost, 12000)
        self.assertEqual(entry.lines.get().cost_source, 'purchase')
        detail = self.client.get(response.url)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'برآورد')

    def test_unknown_reference_cost_is_reported_as_unpriced(self):
        Material.objects.filter(pk=self.material.pk).update(default_unit_price=0)
        response = self.client.post(reverse('procurement_waste_add'), self.entry_data('waste'))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.manager)
        response = self.client.get(reverse('studio_procurement'), {'period': 'today'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['report']['unpriced_count'], 1)
        self.assertEqual(response.context['report']['reference_cost_count'], 1)

    def test_material_edits_require_fresh_version_and_preserve_used_base_unit(self):
        self.service_purchase()
        url = reverse('procurement_material_edit', args=[self.material.pk])
        form = self.client.get(url).context['form']
        data = dict(form.initial)
        data.update(name='رز هلندی', base_unit='شاخه', purchase_unit='بسته', units_per_purchase='۲۰',
            default_unit_price='۳۰۰.۰۰۰', is_active='on')
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.material.refresh_from_db()
        self.assertEqual(self.material.name, 'رز هلندی')
        self.assertEqual(self.client.post(url, {**data, 'name': 'تغییر قدیمی'}).status_code, 400)
        data['version'] = record_version(self.material)
        self.assertEqual(self.client.post(url, {**data, 'base_unit': 'کیلو'}).status_code, 400)
        self.material.refresh_from_db()
        self.assertEqual(self.material.base_unit, 'شاخه')

    def test_void_requires_post_reason_and_current_version_then_keeps_audit(self):
        for kind, record in [('purchase', self.service_purchase()), ('waste', self.service_waste())]:
            with self.subTest(kind=kind):
                url = reverse(f'procurement_{kind}_void', args=[record.pk])
                self.assertEqual(self.client.get(url).status_code, 405)
                for data in ({'version': record_version(record)}, {'version': 'stale', 'reason': 'ثبت تکراری'}):
                    self.assertEqual(self.client.post(url, data).status_code, 400)
                response = self.client.post(url, {'version': record_version(record), 'reason': 'ثبت تکراری'})
                self.assertEqual(response.status_code, 302)
                record.refresh_from_db()
                self.assertEqual(record.status, 'VOID')
                self.assertEqual(record.voided_by_id, self.buyer.pk)
                self.assertEqual(record.void_reason, 'ثبت تکراری')
                self.assertTrue(ProcurementAudit.objects.filter(target_type=record._meta.model_name,
                    target_id=record.pk, action='void').exists())
                detail = self.client.get(reverse(f'procurement_{kind}_detail', args=[record.pk]))
                self.assertContains(detail, 'ثبت تکراری')

    def test_manager_custom_jalali_report_and_ledgers_keep_cost_categories_separate(self):
        excluded = self.service_purchase(day=date(2026, 10, 5), price=100000)
        self.service_purchase(day=date(2026, 10, 6), price=250000)
        voided = self.service_purchase(day=date(2026, 10, 6), price=500000)
        void_purchase(actor=self.buyer, pk=voided.pk, expected_version=record_version(voided), reason='ثبت تکراری')
        self.service_waste(day=date(2026, 10, 6))
        self.client.force_login(self.manager)
        period = {'period': 'custom', 'start_jalali': '۱۴۰۵/۰۷/۱۴', 'end_jalali': '۱۴۰۵/۰۷/۱۴'}
        response = self.client.get(reverse('studio_procurement'), period)
        self.assertEqual(response.status_code, 200)
        report = response.context['report']
        self.assertEqual(report['purchase_total'], 250000)
        self.assertEqual(report['invoice_count'], 1)
        self.assertEqual(report['waste_estimated_total'], 50000)
        self.assertEqual(report['waste_count'], 1)
        self.assertEqual(response.context['period']['start'], date(2026, 10, 6))
        ledger = self.client.get(reverse('procurement_purchases'), period)
        listed_ids = {item.pk for item in ledger.context['page']}
        self.assertIn(voided.pk, listed_ids)
        self.assertNotIn(excluded.pk, listed_ids)

    def test_private_pages_are_not_cached_and_writes_require_csrf(self):
        for name in ('procurement_home', 'procurement_materials', 'procurement_purchase_add', 'procurement_waste_add'):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertIn('no-store', response['Cache-Control'])
                self.assertContains(response, 'noindex,nofollow')
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.buyer)
        data = self.entry_data()
        self.assertEqual(client.post(reverse('procurement_purchase_add'), data).status_code, 403)
        self.assertFalse(PurchaseInvoice.objects.exists())

    def test_formset_never_instantiates_more_than_fifty_client_rows(self):
        formset = PurchaseLineFormSet(data={'lines-TOTAL_FORMS': '50000', 'lines-INITIAL_FORMS': '0'}, prefix='lines')
        self.assertEqual(len(formset.forms), 50)
        self.assertFalse(formset.is_valid())
        self.assertTrue(formset.non_form_errors())
