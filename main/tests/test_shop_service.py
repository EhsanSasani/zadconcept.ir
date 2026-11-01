import uuid
from io import StringIO
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from main.models import Category, CustomerProfile, Product, ShopConfiguration, ShopInventory, ShopInventoryAudit, ShopOrder, ShopPayment
from main.shop_payments import GatewayRequest, GatewayVerification, start_payment, toman_to_rial, verify_payment
from main.shop_service import ShopError, adjust_inventory, cancel_order, cart_snapshot, create_order, expire_orders, fulfillment_quote, shop_configuration


class FakeGateway:
    """Only a test adapter; it is never enabled by production configuration."""
    name = "test-only"
    test_only = True
    merchant_id = "test-merchant"
    allowed_hosts = ("payments.example.test",)
    next_result = None

    def request_payment(self, **kwargs):
        return GatewayRequest("authority-" + kwargs["idempotency_key"], "https://payments.example.test/pay")

    def verify_payment(self, **kwargs):
        return self.next_result or GatewayVerification(
            "paid", kwargs["authority"], kwargs["order_id"], kwargs["amount_rial"],
            reference="reference-" + kwargs["authority"], merchant_id=self.merchant_id,
        )


ENABLED = {"SHOP_PAYMENT_ENABLED": True, "SHOP_PAYMENT_BACKEND": "main.tests.test_shop_service.FakeGateway"}


@override_settings(**ENABLED)
class ShopServiceTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="فروشگاه آزمایشی", slug="shop-tests", section="gifts")
        self.customer = get_user_model().objects.create_user(username="shop-customer")
        CustomerProfile.objects.create(user=self.customer, phone="+989123456789")
        self.other = get_user_model().objects.create_user(username="shop-other")
        CustomerProfile.objects.create(user=self.other, phone="+989123456780")
        self.manager = get_user_model().objects.create_superuser(username="shop-manager", email="", password="test")
        self.product = Product.objects.create(
            category=self.category, catalog_scope="shop", name="محصول فروشگاه",
            pricing_type="fixed", price=125000, publish_status="published",
        )
        self.inventory = ShopInventory.objects.create(product=self.product, quantity=3)
        FakeGateway.next_result = None

    def order(self, **kwargs):
        data = dict(customer=self.customer, cart={str(self.product.pk): 2}, nonce=uuid.uuid4(),
                    expected_total=250000, recipient_name="مشتری", recipient_phone="09123456789")
        data.update(kwargs)
        return create_order(**data)

    def payment(self, order=None):
        order = order or self.order()
        start_payment(order=order, callback_url="https://www.zadconcept.ir/payment/verify/")
        return order.payments.get()

    def stock(self):
        self.inventory.refresh_from_db()
        return self.inventory.quantity

    def test_shop_scope_does_not_leak_into_existing_catalogs(self):
        self.assertFalse(Product.objects.for_general_catalog().filter(pk=self.product.pk).exists())
        self.assertFalse(Product.objects.for_same_day().filter(pk=self.product.pk).exists())
        self.assertFalse(Product.objects.for_weddings().filter(pk=self.product.pk).exists())
        self.assertTrue(Product.objects.for_shop().filter(pk=self.product.pk).exists())

    def test_only_shop_products_can_enter_cart(self):
        for scope in ("general", "same_day"):
            category = self.category
            if scope == "same_day":
                category = Category.objects.create(name="گل", slug="shop-test-flowers", section="flowers")
            product = Product.objects.create(category=category, catalog_scope=scope, pricing_type="fixed", price=1000, publish_status="published")
            snapshot = cart_snapshot({str(product.pk): 1})
            self.assertFalse(snapshot.is_valid)
            self.assertTrue(snapshot.errors)
            with self.assertRaises(ShopError):
                self.order(cart={str(product.pk): 1}, expected_total=1000)
        self.assertEqual(self.stock(), 3)

    def test_snapshot_uses_server_price_and_rejects_malformed_quantities(self):
        snapshot = cart_snapshot({str(self.product.pk): 2})
        self.assertTrue(snapshot.is_valid)
        self.assertEqual(snapshot.total_toman, 250000)
        for quantity in (0, -1, 100, True, 1.5, "2.0", {"quantity": 1}):
            with self.subTest(quantity=quantity):
                self.assertFalse(cart_snapshot({str(self.product.pk): quantity}).is_valid)

    def test_draft_unavailable_and_nonpositive_price_cannot_be_bought(self):
        for field, value in (("publish_status", "draft"), ("stock_status", "out_of_stock"), ("price", 0), ("status", "SOLD")):
            Product.objects.filter(pk=self.product.pk).update(**{field: value})
            self.assertFalse(cart_snapshot({str(self.product.pk): 1}).is_valid)
            with self.assertRaises(ShopError):
                self.order()
            Product.objects.filter(pk=self.product.pk).update(publish_status="published", stock_status="in_stock", price=125000, status="AVAILABLE")
        self.assertEqual(self.stock(), 3)

    @override_settings(SHOP_PAYMENT_ENABLED=False)
    def test_disabled_gateway_never_creates_order_or_reserves_stock(self):
        with self.assertRaises(ShopError) as caught:
            self.order()
        self.assertEqual(caught.exception.code, "payment_disabled")
        self.assertFalse(ShopOrder.objects.exists())
        self.assertEqual(self.stock(), 3)

    def test_authenticated_staff_or_unverified_regular_user_cannot_checkout(self):
        for customer in (self.manager, get_user_model().objects.create_user(username="no-profile")):
            with self.assertRaises(ShopError) as caught:
                self.order(customer=customer)
            self.assertEqual(caught.exception.code, "customer_required")

    def test_price_change_and_insufficient_stock_are_atomic(self):
        with self.assertRaises(ShopError) as caught:
            self.order(expected_total=1)
        self.assertEqual(caught.exception.code, "price_changed")
        self.assertEqual(self.stock(), 3)
        with self.assertRaises(ShopError):
            self.order(cart={str(self.product.pk): 4}, expected_total=500000)
        self.assertEqual(self.stock(), 3)
        self.assertFalse(ShopOrder.objects.exists())

    def test_order_nonce_is_idempotent_and_owner_bound(self):
        nonce = uuid.uuid4()
        order = self.order(nonce=nonce)
        duplicate = self.order(nonce=nonce)
        self.assertEqual(order.pk, duplicate.pk)
        self.assertEqual(self.stock(), 1)
        with self.assertRaises(ShopError):
            self.order(nonce=nonce, customer=self.other)
        with self.assertRaises(ShopError):
            self.order(nonce=nonce, cart={str(self.product.pk): 1}, expected_total=125000)
        self.assertEqual(self.stock(), 1)

    def test_same_nonce_rejects_changed_recipient_or_note(self):
        nonce = uuid.uuid4()
        self.order(nonce=nonce)
        for changes in ({"recipient_name": "گیرندهٔ دیگر"}, {"recipient_phone": "09123456780"}, {"customer_note": "یادداشت جدید"}):
            with self.assertRaises(ShopError) as caught:
                self.order(nonce=nonce, **changes)
            self.assertEqual(caught.exception.code, "request_changed")
        self.assertEqual(self.stock(), 1)

    def test_second_buyer_cannot_consume_already_reserved_units(self):
        self.order()
        with self.assertRaises(ShopError):
            self.order(customer=self.other)
        self.assertEqual(self.stock(), 1)
        self.assertEqual(ShopOrder.objects.count(), 1)

    def test_cancel_and_expiry_release_exactly_once_and_check_owner(self):
        order = self.order()
        with self.assertRaises(ShopError):
            cancel_order(customer=self.other, order_id=order.pk)
        cancel_order(customer=self.customer, order_id=order.pk)
        cancel_order(customer=self.customer, order_id=order.pk)
        self.assertEqual(self.stock(), 3)
        second = self.order()
        ShopOrder.objects.filter(pk=second.pk).update(reserved_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(expire_orders(), 1)
        self.assertEqual(expire_orders(), 0)
        self.assertEqual(self.stock(), 3)

    def test_ambiguous_old_orders_cannot_starve_expiry_of_clear_orders(self):
        old_time = timezone.now() - timedelta(days=1)
        ambiguous = [ShopOrder(customer=self.customer, nonce=uuid.uuid4(), total_toman=125000,
                               items_total_toman=125000, recipient_name="مشتری", recipient_phone="+989123456789",
                               reserved_until=old_time) for _ in range(100)]
        ShopOrder.objects.bulk_create(ambiguous)
        ShopPayment.objects.bulk_create([ShopPayment(order=order, provider="test-only", status="review", amount_rial=1250000)
                                         for order in ambiguous])
        clear_order = self.order()
        ShopOrder.objects.filter(pk=clear_order.pk).update(reserved_until=timezone.now() - timedelta(minutes=1))
        self.assertEqual(expire_orders(limit=1), 1)
        clear_order.refresh_from_db()
        self.assertEqual(clear_order.status, "cancelled")
        self.assertEqual(ShopOrder.objects.filter(pk__in=[order.pk for order in ambiguous], status="pending").count(), 100)
        self.assertEqual(self.stock(), 3)

    def test_order_keeps_immutable_price_and_product_name_snapshot(self):
        order = self.order()
        Product.objects.filter(pk=self.product.pk).update(name="ویرایش‌شده", price=500000)
        line = order.lines.get()
        self.assertEqual(line.product_name, "محصول فروشگاه")
        self.assertEqual(line.unit_price_toman, 125000)
        self.assertEqual(line.subtotal_toman, 250000)

    def test_inventory_permission_stale_guard_and_audit(self):
        with self.assertRaises(ShopError):
            adjust_inventory(actor=self.customer, product_id=self.product.pk, quantity=5, expected_version=0, reason="موجودی")
        updated = adjust_inventory(actor=self.manager, product_id=self.product.pk, quantity=5, expected_version=0, reason="افزایش واقعی موجودی")
        self.assertEqual(updated.version, 1)
        self.assertEqual(self.stock(), 5)
        self.assertEqual(ShopInventoryAudit.objects.get().before, 3)
        with self.assertRaises(ShopError) as caught:
            adjust_inventory(actor=self.manager, product_id=self.product.pk, quantity=50, expected_version=0, reason="فرم قدیمی")
        self.assertEqual(caught.exception.code, "stock_changed")
        self.assertEqual(self.stock(), 5)

    def test_stock_form_opened_before_reservation_cannot_overwrite_reserved_count(self):
        self.order()
        with self.assertRaises(ShopError):
            adjust_inventory(actor=self.manager, product_id=self.product.pk, quantity=3, expected_version=0, reason="فرم قدیمی")
        self.assertEqual(self.stock(), 1)

    def test_nonstaff_operator_with_explicit_shop_permission_can_manage_stock(self):
        operator = get_user_model().objects.create_user(username="shop-operator", is_staff=False)
        operator.user_permissions.add(Permission.objects.get(codename="manage_shop"))
        updated = adjust_inventory(actor=operator, product_id=self.product.pk, quantity=5, expected_version=0, reason="ثبت موجودی واقعی")
        self.assertEqual(updated.quantity, 5)
        self.assertEqual(ShopInventoryAudit.objects.get().actor, operator)

    def test_inventory_rejects_nonshop_product(self):
        product = Product.objects.create(category=self.category, catalog_scope="general")
        with self.assertRaises(ValidationError):
            ShopInventory(product=product).full_clean()
        with self.assertRaises(ShopError):
            adjust_inventory(actor=self.manager, product_id=product.pk, quantity=1, expected_version=0, reason="آزمایش")

    def test_toman_rial_conversion_never_accepts_float_or_nonpositive_values(self):
        self.assertEqual(toman_to_rial(125000), 1250000)
        for value in (0, -1, True, 1.5, "125000"):
            with self.assertRaises(ShopError):
                toman_to_rial(value)

    def test_payment_start_is_idempotent_and_callback_flag_is_not_trusted(self):
        order = self.order()
        with patch.object(FakeGateway, "request_payment", autospec=True, wraps=None) as request:
            request.return_value = GatewayRequest("test-authority", "https://payments.example.test/pay")
            first = start_payment(order=order, callback_url="https://www.zadconcept.ir/payment/verify/")
            second = start_payment(order=order, callback_url="https://www.zadconcept.ir/payment/verify/")
            self.assertEqual(first, second)
            self.assertEqual(request.call_count, 1)
        payment = order.payments.get()
        self.assertEqual(payment.amount_rial, 2500000)
        FakeGateway.next_result = GatewayVerification("pending", payment.authority, str(order.pk), payment.amount_rial, merchant_id=FakeGateway.merchant_id)
        result = verify_payment(authority=payment.authority, callback_status="OK")
        self.assertEqual(result.status, "pending")
        self.assertEqual(self.stock(), 1)

    def test_unknown_request_keeps_stock_and_blocks_second_charge(self):
        order = self.order()
        with patch.object(FakeGateway, "request_payment", side_effect=TimeoutError):
            with self.assertRaises(ShopError):
                start_payment(order=order, callback_url="https://www.zadconcept.ir/payment/verify/")
        self.assertEqual(order.payments.get().status, "review")
        with self.assertRaises(ShopError):
            start_payment(order=order, callback_url="https://www.zadconcept.ir/payment/verify/")
        with self.assertRaises(ShopError):
            cancel_order(customer=self.customer, order_id=order.pk)
        ShopOrder.objects.filter(pk=order.pk).update(reserved_until=timezone.now() - timedelta(hours=1))
        self.assertEqual(expire_orders(), 0)
        self.assertEqual(self.stock(), 1)

    def test_verified_payment_is_idempotent_and_never_restocks(self):
        payment = self.payment()
        paid = verify_payment(authority=payment.authority, callback_status="NOK")
        self.assertEqual(paid.status, "paid")
        self.assertEqual(verify_payment(authority=payment.authority).pk, paid.pk)
        self.assertEqual(self.stock(), 1)
        with self.assertRaises(ShopError):
            cancel_order(customer=self.customer, order_id=paid.pk)

    def test_mismatched_amount_order_authority_and_merchant_never_mark_paid(self):
        payment = self.payment()
        good = GatewayVerification("paid", payment.authority, str(payment.order_id), payment.amount_rial, "reference", FakeGateway.merchant_id)
        for changes in ({"amount_rial": 1}, {"amount_rial": float(payment.amount_rial)}, {"order_id": str(uuid.uuid4())}, {"authority": "forged"}, {"merchant_id": "other"}):
            FakeGateway.next_result = replace(good, **changes)
            with self.assertRaises(ShopError):
                verify_payment(authority=payment.authority, callback_status="OK")
            payment.order.refresh_from_db()
            self.assertEqual(payment.order.status, "pending")
            self.assertEqual(self.stock(), 1)

    def test_rejection_releases_once_and_late_success_requires_review(self):
        payment = self.payment()
        FakeGateway.next_result = GatewayVerification("rejected", payment.authority, str(payment.order_id), payment.amount_rial, merchant_id=FakeGateway.merchant_id)
        order = verify_payment(authority=payment.authority)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(self.stock(), 3)
        verify_payment(authority=payment.authority)
        self.assertEqual(self.stock(), 3)
        FakeGateway.next_result = None
        order = verify_payment(authority=payment.authority)
        payment.refresh_from_db()
        self.assertEqual(order.status, "review")
        self.assertEqual(payment.status, "review")
        self.assertEqual(payment.last_error, "late_payment_review")
        self.assertEqual(self.stock(), 3)

    def test_duplicate_provider_reference_cannot_pay_two_orders(self):
        first = self.payment(self.order(cart={str(self.product.pk): 1}, expected_total=125000))
        FakeGateway.next_result = GatewayVerification("paid", first.authority, str(first.order_id), first.amount_rial, "same-reference", FakeGateway.merchant_id)
        verify_payment(authority=first.authority)
        second = self.payment(self.order(cart={str(self.product.pk): 1}, expected_total=125000))
        FakeGateway.next_result = replace(FakeGateway.next_result, authority=second.authority, order_id=str(second.order_id))
        with self.assertRaises(ShopError) as caught:
            verify_payment(authority=second.authority)
        self.assertEqual(caught.exception.code, "transaction_conflict")
        second.order.refresh_from_db()
        self.assertEqual(second.order.status, "pending")
        self.assertEqual(ShopPayment.objects.filter(status="paid").count(), 1)

    def test_database_prevents_negative_stock(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ShopInventory.objects.filter(pk=self.inventory.pk).update(quantity=-1)

    @override_settings(IS_PRODUCTION=True)
    def test_production_refuses_test_only_gateway(self):
        with self.assertRaises(ShopError) as caught:
            self.order()
        self.assertEqual(caught.exception.code, "payment_unavailable")
        self.assertEqual(self.stock(), 3)
        self.assertFalse(ShopOrder.objects.exists())

    def test_reconciliation_verifies_known_authority_and_keeps_request_unknown_reserved(self):
        payment = self.payment(self.order(cart={str(self.product.pk): 1}, expected_total=125000))
        unknown = self.order(cart={str(self.product.pk): 1}, expected_total=125000)
        ShopPayment.objects.create(order=unknown, provider=FakeGateway.name, status="review", amount_rial=1250000)
        output = StringIO()
        call_command("reconcile_shop_payments", stdout=output)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "paid")
        unknown.refresh_from_db()
        self.assertEqual(unknown.status, "pending")
        self.assertEqual(self.stock(), 1)
        self.assertIn("paid=1", output.getvalue())
        self.assertIn("request_unknown_manual_review=1", output.getvalue())
        self.assertNotIn(payment.authority, output.getvalue())
        self.assertNotIn(self.customer.customer_profile.phone, output.getvalue())

    def test_unconfigured_shipping_has_no_implicit_free_delivery(self):
        self.assertTrue(shop_configuration()._state.adding)
        self.assertFalse(ShopConfiguration.objects.exists())
        self.assertEqual(fulfillment_quote("pickup"), 0)
        with self.assertRaises(ShopError):
            fulfillment_quote("delivery")
        with self.assertRaises(ShopError):
            self.order(fulfillment="delivery", recipient_address="مشهد، نشانی کامل برای ارسال")
        self.assertEqual(self.stock(), 3)
        self.assertFalse(ShopOrder.objects.exists())

    def test_delivery_snapshots_explicit_fee_address_and_final_payable_amount(self):
        config = ShopConfiguration.objects.create(delivery_enabled=True, delivery_fee_toman=50000)
        order = self.order(fulfillment="delivery", recipient_address="مشهد، خیابان احمدآباد، پلاک ۱۰", expected_total=300000)
        self.assertEqual(order.items_total_toman, 250000)
        self.assertEqual(order.shipping_fee_toman, 50000)
        self.assertEqual(order.total_toman, 300000)
        self.assertEqual(order.recipient_city, "مشهد")
        config.delivery_fee_toman = 90000
        config.save()
        order.refresh_from_db()
        self.assertEqual(order.shipping_fee_toman, 50000)
        payment = self.payment(order)
        self.assertEqual(payment.amount_rial, 3000000)

    def test_changed_shipping_fee_requires_new_confirmation_without_reserving(self):
        config = ShopConfiguration.objects.create(delivery_enabled=True, delivery_fee_toman=50000)
        quoted = fulfillment_quote("delivery")
        config.delivery_fee_toman = 90000
        config.save()
        with self.assertRaises(ShopError) as caught:
            self.order(fulfillment="delivery", recipient_address="مشهد، خیابان احمدآباد، پلاک ۱۰", expected_total=250000 + quoted)
        self.assertEqual(caught.exception.code, "price_changed")
        self.assertEqual(self.stock(), 3)

    def test_delivery_rejects_other_city_missing_address_and_disabled_pickup(self):
        ShopConfiguration.objects.create(pickup_enabled=False, delivery_enabled=True, delivery_fee_toman=0)
        for values in ({"recipient_city": "تهران", "recipient_address": "تهران، خیابان ولیعصر، پلاک ۱۰"}, {"recipient_address": ""}):
            with self.assertRaises(ShopError):
                self.order(fulfillment="delivery", **values)
        with self.assertRaises(ShopError):
            self.order()
        order = self.order(fulfillment="delivery", recipient_address="مشهد، خیابان احمدآباد، پلاک ۱۰")
        self.assertEqual(order.shipping_fee_toman, 0)

    def test_shipping_configuration_requires_explicit_fee_and_one_active_method(self):
        with self.assertRaises(ValidationError):
            ShopConfiguration(delivery_enabled=True, delivery_fee_toman=None).full_clean()
        with self.assertRaises(ValidationError):
            ShopConfiguration(pickup_enabled=False, delivery_enabled=False).full_clean()
        with self.assertRaises(ValidationError):
            ShopConfiguration(delivery_enabled=True, delivery_fee_toman=1000000000001).full_clean()
