from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from main.customer_auth import (is_customer, login_customer, normalize_phone,
                                register_customer, safe_destination)
from main.models import CustomerLoginRate, CustomerProfile


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CustomerAuthTests(TestCase):
    password = "cedar-Cobalt!7308"

    def setUp(self):
        self.user = register_customer("09151234567", self.password)

    def test_phone_formats_normalize_without_guessing_foreign_numbers(self):
        for value in ["۰۹۱۵۱۲۳۴۵۶۷", "٠٩١٥١٢٣٤٥٦٧", "+98 915 1234567", "00989151234567"]:
            self.assertEqual(normalize_phone(value), "+989151234567")
        for value in ["+14155552671", "9151234567", "091512345678", "phone"]:
            with self.assertRaises(ValidationError):
                normalize_phone(value)

    def test_registration_hashes_password_and_grants_no_staff_role(self):
        self.assertNotEqual(self.user.password, self.password)
        self.assertTrue(self.user.check_password(self.password))
        self.assertTrue(is_customer(self.user))
        self.assertFalse(self.user.is_staff or self.user.is_superuser)
        self.assertFalse(self.user.user_permissions.exists())
        self.assertFalse(self.user.groups.exists())

    def test_weak_password_and_duplicate_phone_create_no_orphan_users(self):
        before = get_user_model().objects.count()
        for phone, password in [("09151234568", "12345678"), ("+989151234567", self.password)]:
            with self.assertRaises(ValidationError):
                register_customer(phone, password)
        self.assertEqual(get_user_model().objects.count(), before)

    def test_wrong_password_and_unknown_phone_have_same_error(self):
        request = RequestFactory().post("/")
        errors = []
        for phone in ["09151234567", "09151234568"]:
            with self.assertRaises(ValidationError) as error:
                login_customer(request, phone, "incorrect")
            errors.append(error.exception.messages)
        self.assertEqual(*errors)

    def test_login_quota_is_database_shared_and_not_locmem(self):
        request = RequestFactory().post("/")
        for _ in range(10):
            with self.assertRaises(ValidationError):
                login_customer(request, "09151234567", "incorrect")
        with self.assertRaises(ValidationError) as error:
            login_customer(request, "09151234567", self.password)
        self.assertIn("تعداد تلاش‌ها", error.exception.messages[0])
        self.assertTrue(CustomerLoginRate.objects.exists())

    def test_privileged_or_disabled_profiles_cannot_use_customer_login(self):
        request = RequestFactory().post("/")
        for field in ["is_staff", "is_superuser"]:
            setattr(self.user, field, True)
            self.user.save()
            with self.assertRaises(ValidationError):
                login_customer(request, "09151234567", self.password)
            setattr(self.user, field, False)
        self.user.is_active = False
        self.user.save()
        with self.assertRaises(ValidationError):
            login_customer(request, "09151234567", self.password)

    def test_staff_phone_username_is_never_matched_to_customer(self):
        staff = get_user_model().objects.create_user(username="09151234568", password=self.password, is_staff=True)
        customer = register_customer("09151234568", self.password)
        self.assertNotEqual(customer.pk, staff.pk)
        self.assertFalse(customer.is_staff)

    def test_login_rotates_session_and_preserves_cart_and_next(self):
        session = self.client.session
        session["shop_cart"] = {"999": 2}
        session["shop_checkout_nonce"] = "draft-nonce"
        session.save()
        old_key = session.session_key
        response = self.client.post(reverse("customer_login"), {
            "phone": "۰۹۱۵۱۲۳۴۵۶۷", "password": self.password, "next": reverse("shop_checkout")})
        self.assertRedirects(response, reverse("shop_checkout"), fetch_redirect_response=False)
        self.assertNotEqual(self.client.session.session_key, old_key)
        self.assertEqual(self.client.session["shop_cart"], {"999": 2})
        self.assertEqual(self.client.session["shop_checkout_nonce"], "draft-nonce")

    def test_next_rejects_external_staff_and_login_destinations(self):
        request = RequestFactory().get("/shop/login/")
        for path in ["https://evil.example/", "//evil.example/", "/studio/", "/admin/", "/shop/login/", "/shop/../admin/"]:
            self.assertEqual(safe_destination(request, path), reverse("customer_account"))

    def test_customer_cannot_open_staff_shop_editor(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("shop_manage")).status_code, 403)

    def test_login_csrf_and_logout_post_only(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("customer_login"), {"phone": "09151234567", "password": self.password}).status_code, 403)
        self.assertEqual(self.client.get(reverse("customer_logout")).status_code, 405)

    def test_registration_mismatch_renders_errors_and_no_account(self):
        response = self.client.post(reverse("customer_register"), {
            "phone": "09151234568", "password1": self.password, "password2": "other"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CustomerProfile.objects.filter(phone="+989151234568").exists())

    def test_logout_preserves_guest_cart_but_removes_identity(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["shop_cart"] = {"6": 1}
        session.save()
        self.client.post(reverse("customer_logout"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.session["shop_cart"], {"6": 1})

    def test_password_change_requires_old_password_and_preserves_login(self):
        self.client.force_login(self.user)
        path = reverse("customer_password")
        new = "Fresh-Cedar!94355"
        invalid = self.client.post(path, {"old_password": "wrong", "new_password1": new, "new_password2": new})
        self.assertEqual(invalid.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.password))
        valid = self.client.post(path, {"old_password": self.password, "new_password1": new, "new_password2": new})
        self.assertRedirects(valid, reverse("customer_account"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
