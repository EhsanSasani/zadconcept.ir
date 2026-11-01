from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from main.models import Category, CustomerProfile, Product, ShopConfiguration, ShopInventory, ShopOrder, ShopOrderLine
from main.panel import workspaces
from main.shop_forms import ShopCheckoutForm
from main.shop_service import ShopError, adjust_inventory


@override_settings(SHOP_PAYMENT_ENABLED=False, SHOP_PAYMENT_BACKEND="")
class ShopViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="دسته آزمایش", slug="shop-test", section="flowers")
        cls.product = Product.objects.create(name="محصول فروشگاه", category=cls.category, catalog_scope="shop",
            pricing_type="fixed", price=120000, cover_image="shop-test.webp", publish_status="published")
        ShopInventory.objects.create(product=cls.product, quantity=5)
        cls.general = Product.objects.create(name="محصول کاتالوگ", category=cls.category,
            pricing_type="fixed", price=90000, cover_image="catalog-test.webp", publish_status="published")
        cls.customer = get_user_model().objects.create_user(username="shop-customer")
        CustomerProfile.objects.create(user=cls.customer, phone="+989121111111")
        cls.other = get_user_model().objects.create_user(username="other-customer")
        CustomerProfile.objects.create(user=cls.other, phone="+989122222222")
        cls.manager = get_user_model().objects.create_user(username="shop-manager", is_staff=True)
        cls.manager.user_permissions.add(Permission.objects.get(codename="manage_shop"))
        cls.staff = get_user_model().objects.create_user(username="unprivileged-staff", is_staff=True)

    def set_cart(self, quantity=1):
        session = self.client.session
        session["shop_cart"] = {str(self.product.pk): quantity}
        session.save()

    def order(self, **kwargs):
        defaults = dict(customer=self.customer, nonce=uuid4(), total_toman=120000, items_total_toman=120000, shipping_fee_toman=0,
            recipient_name="آزمایش", recipient_phone="+989121111111", reserved_until=timezone.now() + timedelta(minutes=20))
        defaults.update(kwargs)
        order = ShopOrder.objects.create(**defaults)
        ShopOrderLine.objects.create(order=order, product=self.product, product_name=self.product.name,
            unit_price_toman=120000, quantity=1)
        return order

    def test_shop_listing_and_detail_do_not_sell_catalog_products(self):
        response = self.client.get(reverse("shop_home"))
        self.assertContains(response, self.product.name)
        self.assertNotContains(response, self.general.name)
        self.assertEqual(self.client.get(reverse("shop_product_detail", args=[self.general.slug])).status_code, 404)
        self.client.post(reverse("shop_cart_update"), {"product_id": self.general.pk, "quantity": 1, "action": "add"})
        self.assertEqual(self.client.session.get("shop_cart", {}), {})

    def test_cart_changes_are_post_only_and_csrf_protected(self):
        self.assertEqual(self.client.get(reverse("shop_cart_update")).status_code, 405)
        protected = Client(enforce_csrf_checks=True)
        self.assertEqual(protected.post(reverse("shop_cart_update"), {"product_id": self.product.pk, "quantity": 1}).status_code, 403)

    def test_cart_rejects_quantity_over_stock_without_erasing_previous_cart(self):
        self.set_cart(2)
        self.client.post(reverse("shop_cart_update"), {"product_id": self.product.pk, "quantity": 9, "action": "set"})
        self.assertEqual(self.client.session["shop_cart"], {str(self.product.pk): 2})
        self.assertEqual(ShopInventory.objects.get(product=self.product).quantity, 5)

    def test_cart_normalizes_persian_quantity_and_removes_without_get_mutation(self):
        self.client.post(reverse("shop_cart_update"), {"product_id": self.product.pk, "quantity": "۲", "action": "add"})
        self.assertEqual(self.client.session["shop_cart"], {str(self.product.pk): 2})
        self.client.post(reverse("shop_cart_update"), {"product_id": self.product.pk, "action": "remove"})
        self.assertEqual(self.client.session["shop_cart"], {})

    def test_checkout_requires_customer_login_and_preserves_cart(self):
        self.set_cart()
        response = self.client.get(reverse("shop_checkout"))
        self.assertRedirects(response, reverse("customer_login") + "?next=" + reverse("shop_checkout"))
        self.assertEqual(self.client.session["shop_cart"], {str(self.product.pk): 1})

    def test_disabled_checkout_does_not_create_order_or_reserve_stock(self):
        self.client.force_login(self.customer)
        self.set_cart()
        response = self.client.post(reverse("shop_checkout"), {"recipient_name": "مشتری", "recipient_phone": "+989121111111",
            "fulfillment": "pickup", "accept_terms": "on", "expected_total": 120000})
        self.assertContains(response, "پرداخت آنلاین فعلاً در دسترس نیست")
        self.assertContains(response, " disabled")
        self.assertFalse(ShopOrder.objects.exists())
        self.assertEqual(ShopInventory.objects.get(product=self.product).quantity, 5)

    def test_checkout_form_accepts_profile_phone_but_rejects_delivery_and_missing_terms(self):
        persian_phone = "+989121111111".translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        form = ShopCheckoutForm({"recipient_name": "مشتری", "recipient_phone": persian_phone,
            "fulfillment": "pickup", "accept_terms": "on", "expected_total": 120000})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["recipient_phone"], "+989121111111")
        form = ShopCheckoutForm({"recipient_name": "مشتری", "recipient_phone": "09121111111",
            "fulfillment": "delivery", "expected_total": 120000})
        self.assertIn("fulfillment", form.errors)
        self.assertIn("accept_terms", form.errors)

    def test_price_change_requires_resubmit_with_visible_current_total(self):
        self.client.force_login(self.customer)
        self.set_cart()
        with patch("main.shop_views.shop_payments.payment_enabled", return_value=True), patch(
            "main.shop_views.shop_service.create_order") as create_order:
            response = self.client.post(reverse("shop_checkout"), {"recipient_name": "مشتری", "recipient_phone": "09121111111",
                "fulfillment": "pickup", "accept_terms": "on", "expected_total": 100000})
        self.assertContains(response, "مبلغ سفارش یا روش دریافت تغییر کرده است")
        create_order.assert_not_called()
        self.assertContains(response, 'name="expected_total" value="120000"', html=False)
        self.assertFalse(ShopOrder.objects.exists())

    def test_manager_requires_explicit_shop_permission(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("shop_manage")).status_code, 403)
        self.assertNotIn("shop", [item["key"] for item in workspaces(self.staff)])
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("shop_manage")).status_code, 200)
        self.assertIn("shop", [item["key"] for item in workspaces(self.manager)])

    def test_manager_cannot_edit_catalog_product_through_shop_url(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("shop_manage_product", kwargs={"pk": self.general.pk})).status_code, 404)

    def product_data(self, **overrides):
        data = {"name": "ویرایش فروشگاه", "category": self.category.pk, "price": 150000,
            "is_active": "on", "publish_status": "published", "sort_order": 0,
            "inventory_quantity": 7, "inventory_version": 0, "inventory_reason": "ورود کالای تازه"}
        data.update(overrides)
        return data

    def test_manager_stock_version_conflict_rolls_back_product_edit(self):
        adjust_inventory(actor=self.manager, product_id=self.product.pk, quantity=4, expected_version=0, reason="اصلاح موجودی")
        self.client.force_login(self.manager)
        response = self.client.post(reverse("shop_manage_product", kwargs={"pk": self.product.pk}), self.product_data())
        self.assertContains(response, "موجودی تغییر کرده است")
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "محصول فروشگاه")
        self.assertEqual(int(self.product.price), 120000)
        self.assertEqual(ShopInventory.objects.get(product=self.product).quantity, 4)

    def test_manager_saves_shop_only_with_stock_audit(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("shop_manage_product", kwargs={"pk": self.product.pk}),
            self.product_data(catalog_scope="general"))
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.catalog_scope, "shop")
        self.assertEqual(ShopInventory.objects.get(product=self.product).quantity, 7)
        self.assertEqual(self.product.shop_stock_audits.get().actor, self.manager)

    def test_orders_are_owner_only_and_staff_order_screen_is_separate(self):
        order = self.order()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("shop_order_detail", kwargs={"order_id": order.pk})).status_code, 404)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("shop_order_detail", kwargs={"order_id": order.pk})).status_code, 200)
        self.assertEqual(self.client.get(reverse("shop_manage_orders")).status_code, 403)

    def test_delayed_paid_callback_does_not_discard_newer_cart(self):
        order = self.order(status="paid", paid_at=timezone.now())
        self.client.force_login(self.customer)
        self.set_cart(3)
        session = self.client.session
        session["shop_checkout_nonce"] = str(order.nonce)
        session.save()
        with patch("main.shop_views.shop_payments.verify_payment", return_value=order) as verify:
            response = self.client.get(reverse("shop_payment_callback"), {"Authority": "known", "Status": "OK"})
        verify.assert_called_once_with(authority="known", callback_status="OK")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["shop_cart"], {str(self.product.pk): 3})

    def test_forged_success_callback_does_not_mark_order_paid(self):
        order = self.order()
        with patch("main.shop_views.shop_payments.verify_payment", side_effect=ShopError("not_found", "تراکنش پیدا نشد")):
            response = self.client.get(reverse("shop_payment_callback"), {"Authority": "fake", "Status": "OK"})
        self.assertContains(response, "نتیجه پرداخت نیاز به بررسی دارد")
        order.refresh_from_db()
        self.assertEqual(order.status, "pending")

    def test_matching_paid_callback_clears_cart_once_only(self):
        order = self.order(status="paid", paid_at=timezone.now())
        self.client.force_login(self.customer)
        self.set_cart()
        session = self.client.session
        session["shop_checkout_nonce"] = str(order.nonce)
        session.save()
        with patch("main.shop_views.shop_payments.verify_payment", return_value=order):
            self.client.get(reverse("shop_payment_callback"), {"Authority": "known", "Status": "OK"})
            self.assertEqual(self.client.session["shop_cart"], {})
            self.set_cart(2)
            self.client.get(reverse("shop_payment_callback"), {"Authority": "known", "Status": "OK"})
        self.assertEqual(self.client.session["shop_cart"], {str(self.product.pk): 2})

    def test_cancelling_order_releases_checkout_nonce_for_new_attempt(self):
        order = self.order()
        self.client.force_login(self.customer)
        session = self.client.session
        session["shop_checkout_nonce"] = str(order.nonce)
        session.save()
        self.client.post(reverse("shop_order_cancel", kwargs={"order_id": order.pk}))
        self.assertNotIn("shop_checkout_nonce", self.client.session)

    def test_delivery_fee_change_requires_review_and_preserves_address(self):
        ShopConfiguration.objects.create(pk=1, delivery_enabled=True, delivery_fee_toman=50000)
        self.client.force_login(self.customer)
        self.set_cart()
        with patch("main.shop_views.shop_payments.payment_enabled", return_value=True), patch(
            "main.shop_views.shop_service.create_order") as create_order:
            response = self.client.post(reverse("shop_checkout"), {"recipient_name": "مشتری", "recipient_phone": "09121111111",
                "fulfillment": "delivery", "recipient_address": "مشهد خیابان آزمایش پلاک یک", "accept_terms": "on", "expected_total": 120000})
        create_order.assert_not_called()
        self.assertContains(response, 'name="expected_total" value="170000"')
        self.assertContains(response, "مشهد خیابان آزمایش پلاک یک")
        self.assertFalse(ShopOrder.objects.exists())

    def test_shipping_settings_require_explicit_fee_before_enabling(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("shop_manage_settings"), {"pickup_enabled": "on", "delivery_enabled": "on", "delivery_fee_toman": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ShopConfiguration.objects.filter(delivery_enabled=True).exists())
        self.client.post(reverse("shop_manage_settings"), {"pickup_enabled": "on", "delivery_enabled": "on", "delivery_fee_toman": 0})
        configuration = ShopConfiguration.objects.get(pk=1)
        self.assertTrue(configuration.delivery_enabled)
        self.assertEqual(configuration.delivery_fee_toman, 0)

    def test_unpublished_cart_item_can_be_removed_without_erasing_other_selections(self):
        hidden = Product.objects.create(name="مورد خارج‌شده", category=self.category, catalog_scope="shop",
            pricing_type="fixed", price=100000, cover_image="hidden-test.webp", publish_status="published")
        ShopInventory.objects.create(product=hidden, quantity=1)
        Product.objects.filter(pk=hidden.pk).update(is_active=False)
        session = self.client.session
        session["shop_cart"] = {str(self.product.pk): 2, str(hidden.pk): 1}
        session.save()
        response = self.client.get(reverse("shop_cart"))
        self.assertContains(response, 'name="product_id" value="' + str(hidden.pk) + '"')
        self.client.post(reverse("shop_cart_update"), {"product_id": hidden.pk, "action": "remove"})
        self.assertEqual(self.client.session["shop_cart"], {str(self.product.pk): 2})

    def test_oversized_category_filter_does_not_crash_public_shop(self):
        response = self.client.get(reverse("shop_home"), {"category": "9" * 5000})
        self.assertEqual(response.status_code, 200)

    def test_fulfillment_quote_is_available_without_gateway_or_personal_fields(self):
        ShopConfiguration.objects.create(pk=1, delivery_enabled=True, delivery_fee_toman=50000)
        self.client.force_login(self.customer)
        self.set_cart()
        for gateway_enabled in (False, True):
            with self.subTest(gateway_enabled=gateway_enabled), patch(
                "main.shop_views.shop_payments.payment_enabled", return_value=gateway_enabled), patch(
                "main.shop_views.shop_service.create_order") as create_order, patch(
                "main.shop_views.shop_payments.start_payment") as start_payment:
                response = self.client.post(reverse("shop_checkout"), {"action": "review", "fulfillment": "delivery",
                    "recipient_name": "نام پیش‌نویس", "customer_note": "یادداشت حفظ‌شده", "expected_total": 120000})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context["form"].errors)
                self.assertTrue(response.context["form"].fields["recipient_address"].required)
                self.assertContains(response, '<label for="id_recipient_address">آدرس دریافت در مشهد</label>')
                self.assertEqual(response.context["total_toman"], 170000)
                self.assertContains(response, 'name="expected_total" value="170000"')
                self.assertContains(response, "نام پیش‌نویس")
                self.assertContains(response, "یادداشت حفظ‌شده")
                create_order.assert_not_called()
                start_payment.assert_not_called()
        self.assertFalse(ShopOrder.objects.exists())
        self.assertEqual(ShopInventory.objects.get(product=self.product).quantity, 5)

    def test_public_shop_has_configured_canonical_but_cart_is_not_indexable(self):
        from main.seo import absolute_site_url
        listing = self.client.get(reverse("shop_home"))
        self.assertContains(listing, '<link rel="canonical" href="' + absolute_site_url(reverse("shop_home")) + '">')
        detail = self.client.get(reverse("shop_product_detail", args=[self.product.slug]))
        from django.utils.encoding import iri_to_uri
        self.assertEqual(iri_to_uri(detail.context["canonical_url"]), absolute_site_url(self.product.get_absolute_url()))
        self.assertContains(detail, '<link rel="canonical" href="' + detail.context["canonical_url"] + '">')
        self.assertContains(self.client.get(reverse("shop_cart")), '<meta name="robots" content="noindex,nofollow">')
