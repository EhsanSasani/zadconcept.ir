from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from main.account_forms import AccountForm
from main.account_roles import account_version, assigned_roles, editable_account
from main.account_service import save_account, save_technical_florist_link
from main.customer_auth import _limit, login_customer, requester_ip
from main.models import CustomerProfile
from main.panel import workspaces


class ShopRequesterIPTests(SimpleTestCase):
    def request(self, remote="", real_ip="", forwarded=""):
        return RequestFactory().get("/shop/login/", REMOTE_ADDR=remote,
            HTTP_X_REAL_IP=real_ip, HTTP_X_FORWARDED_FOR=forwarded)

    @override_settings(SHOP_TRUST_PROXY_IP=False)
    def test_untrusted_headers_never_override_remote_or_empty_socket_address(self):
        self.assertEqual(requester_ip(self.request("192.0.2.1", "198.51.100.2")), "192.0.2.1")
        self.assertEqual(requester_ip(self.request("", "198.51.100.2")), "unknown")
        self.assertEqual(requester_ip(self.request("", "", "198.51.100.2")), "unknown")

    @override_settings(SHOP_TRUST_PROXY_IP=True)
    def test_configured_local_proxy_uses_valid_real_ip_for_socket_and_loopback(self):
        for remote in ("", "127.0.0.1", "::1"):
            with self.subTest(remote=remote):
                self.assertEqual(requester_ip(self.request(remote, "198.51.100.2")), "198.51.100.2")
        self.assertEqual(requester_ip(self.request("", "2001:db8::1")), "2001:db8::1")

    @override_settings(SHOP_TRUST_PROXY_IP=True)
    def test_remote_client_cannot_spoof_proxy_header_even_when_proxy_mode_enabled(self):
        self.assertEqual(requester_ip(self.request("192.0.2.1", "198.51.100.2")), "192.0.2.1")
        self.assertEqual(requester_ip(self.request("invalid", "198.51.100.2")), "unknown")

    @override_settings(SHOP_TRUST_PROXY_IP=True)
    def test_invalid_real_ip_and_forwarded_list_are_not_trusted(self):
        for value in ("invalid", "198.51.100.2, 198.51.100.3", ""):
            with self.subTest(value=value):
                self.assertEqual(requester_ip(self.request("127.0.0.1", value)), "127.0.0.1")
        self.assertEqual(requester_ip(self.request("", "", "198.51.100.2")), "unknown")


@override_settings(SHOP_TRUST_PROXY_IP=True)
class ShopProxyQuotaTests(TestCase):
    def test_distinct_proxy_clients_have_distinct_ip_quotas(self):
        factory = RequestFactory()
        first = factory.get("/", REMOTE_ADDR="", HTTP_X_REAL_IP="198.51.100.1")
        second = factory.get("/", REMOTE_ADDR="", HTTP_X_REAL_IP="198.51.100.2")
        phones = [f"+98915123456{index}" for index in range(5)]
        for index in range(40):
            _limit(phones[index % len(phones)], requester_ip(first), "login")
        with self.assertRaises(ValidationError):
            _limit(phones[0], requester_ip(first), "login")
        _limit(phones[0], requester_ip(second), "login")

    def test_login_and_registration_both_use_the_trusted_client_ip(self):
        request = RequestFactory().post("/shop/login/", REMOTE_ADDR="", HTTP_X_REAL_IP="198.51.100.7")
        with patch("main.customer_auth._limit") as limit:
            with self.assertRaises(ValidationError):
                login_customer(request, "09151234567", "invalid-password")
            limit.assert_called_once_with("+989151234567", "198.51.100.7", "login")
        with patch("main.customer_auth.register_customer", side_effect=ValidationError("ثبت نشد")) as register:
            response = self.client.post(reverse("customer_register"), {
                "phone": "09151234567", "password1": "cedar-Cobalt!7308", "password2": "cedar-Cobalt!7308",
            }, REMOTE_ADDR="", HTTP_X_REAL_IP="198.51.100.8")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(register.call_args.args[3], "198.51.100.8")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ShopRoleTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username="shop-account-manager")
        self.actor.user_permissions.add(Permission.objects.get(codename="manage_studio_accounts"))

    def form(self, *, user=None, roles=None, is_active=True):
        data = {"username": user.username if user else "shop-only-operator", "first_name": "مسئول فروشگاه",
            "last_name": "", "email": "", "roles": ["shop"] if roles is None else roles,
            "is_active": is_active, "version": account_version(user) if user else "",
            "password1": "" if user else "cedar-Cobalt!7308", "password2": "" if user else "cedar-Cobalt!7308"}
        form = AccountForm(data=data, user=user)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        return form

    def test_account_editor_grants_shop_only_without_staff_or_other_operational_roles(self):
        user = save_account(actor=self.actor, data=self.form().cleaned_data)
        self.assertTrue(editable_account(user))
        self.assertEqual(assigned_roles(user), ["shop"])
        self.assertEqual(user.get_all_permissions(), {"main.manage_shop"})
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual([item["key"] for item in workspaces(user)], ["shop"])
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("shop_manage")).status_code, 200)

    def test_shop_role_can_be_preserved_and_removed_through_existing_account_editor(self):
        user = save_account(actor=self.actor, data=self.form().cleaned_data)
        user = save_account(actor=self.actor, user_id=user.pk, data=self.form(user=user).cleaned_data)
        self.assertEqual(assigned_roles(user), ["shop"])
        user = save_account(actor=self.actor, user_id=user.pk,
            data=self.form(user=user, roles=[], is_active=False).cleaned_data)
        self.assertEqual(assigned_roles(user), [])
        self.assertFalse(user.is_active)
        self.assertFalse(user.groups.filter(permissions__codename="manage_shop").exists())

    def test_existing_manager_does_not_gain_shop_without_explicit_grant(self):
        manager = get_user_model().objects.create_user(username="existing-studio-manager")
        manager.user_permissions.add(Permission.objects.get(codename="view_studioproduct"))
        manager = save_account(actor=self.actor, user_id=manager.pk,
            data=self.form(user=manager, roles=["manager"]).cleaned_data)
        self.assertFalse(manager.has_perm("main.manage_shop"))
        self.assertNotIn("shop", assigned_roles(manager))

    def test_cli_can_provision_shop_role_and_still_provision_older_roles(self):
        shop_user = get_user_model().objects.create_user(username="shop-cli")
        sales_user = get_user_model().objects.create_user(username="sales-cli")
        call_command("studio_account", shop_user.username, shop=True, stdout=StringIO())
        call_command("studio_account", sales_user.username, sales=True, stdout=StringIO())
        self.assertEqual(assigned_roles(shop_user), ["shop"])
        self.assertEqual(assigned_roles(sales_user), ["sales"])
        self.assertEqual(shop_user.get_all_permissions(), {"main.manage_shop"})

    def test_customers_are_excluded_from_staff_list_and_cannot_be_converted_by_staff_editor(self):
        customer = get_user_model().objects.create_user(username="private-shop-customer", first_name="مشتری خصوصی")
        CustomerProfile.objects.create(user=customer, phone="+989151234567")
        self.client.force_login(self.actor)
        response = self.client.get(reverse("studio_accounts"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, customer.username)
        self.assertNotContains(response, customer.first_name)
        self.assertFalse(editable_account(customer))
        self.assertEqual(self.client.get(reverse("studio_account_edit", args=[customer.pk])).status_code, 403)
        with self.assertRaises(PermissionDenied):
            save_account(actor=self.actor, user_id=customer.pk, data=self.form(user=customer).cleaned_data)
        self.assertFalse(customer.groups.exists())
        self.assertFalse(customer.user_permissions.exists())

    def test_cli_rejects_customer_identity_before_any_password_prompt_or_role_change(self):
        customer = get_user_model().objects.create_user(username="customer-cli")
        CustomerProfile.objects.create(user=customer, phone="+989151234568")
        with patch("main.management.commands.studio_account.getpass") as prompt:
            with self.assertRaises(CommandError):
                call_command("studio_account", customer.username, shop=True, reset_password=True, stdout=StringIO())
        prompt.assert_not_called()
        self.assertFalse(customer.groups.exists())

    def test_customer_cannot_be_linked_as_technical_florist_either(self):
        customer = get_user_model().objects.create_user(username="customer-no-florist")
        CustomerProfile.objects.create(user=customer, phone="+989151234569")
        root = get_user_model().objects.create_superuser(username="shop-role-root", email="", password="test")
        with self.assertRaises(PermissionDenied):
            save_technical_florist_link(actor=root, user_id=customer.pk,
                data={"version": account_version(customer), "enabled": True, "florist": None})
        self.client.force_login(root)
        self.assertEqual(self.client.get(reverse("studio_account_florist_link", args=[customer.pk])).status_code, 403)
