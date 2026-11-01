"""Real row-lock checks; intentionally skipped by the default SQLite suite."""
import threading
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings

from main.models import Category, CustomerProfile, Product, ShopInventory, ShopInventoryAudit, ShopOrder, ShopPayment
from main.shop_payments import start_payment, verify_payment
from main.shop_service import ShopError, adjust_inventory, create_order
from main.tests.test_shop_service import FakeGateway


class BlockingGateway(FakeGateway):
    entered = threading.Event()
    release = threading.Event()
    calls = 0
    counter_lock = threading.Lock()

    def verify_payment(self, **kwargs):
        with self.counter_lock:
            type(self).calls += 1
        self.entered.set()
        if not self.release.wait(timeout=10):
            raise TimeoutError("test verification gate did not open")
        return super().verify_payment(**kwargs)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks and independent connections")
@override_settings(IS_PRODUCTION=False, SHOP_PAYMENT_ENABLED=True,
                   SHOP_PAYMENT_BACKEND="main.tests.test_shop_service.FakeGateway")
class ShopPostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        category = Category.objects.create(name="هم‌زمانی", slug="shop-concurrency", section="gifts")
        self.product = Product.objects.create(category=category, name="آخرین موجودی", catalog_scope="shop",
                                              pricing_type="fixed", price=125000, publish_status="published")
        self.inventory = ShopInventory.objects.create(product=self.product, quantity=1)
        self.customer_ids = []
        for number in range(2):
            user = get_user_model().objects.create_user(username=f"concurrent-customer-{number}")
            CustomerProfile.objects.create(user=user, phone=f"+98912345678{number}")
            self.customer_ids.append(user.pk)
        self.operator = get_user_model().objects.create_user(username="concurrent-operator")
        self.operator.user_permissions.add(Permission.objects.get(codename="manage_shop"))
        FakeGateway.next_result = None

    def _order(self, user_id):
        user = get_user_model().objects.get(pk=user_id)
        return create_order(customer=user, cart={str(self.product.pk): 1}, nonce=uuid.uuid4(),
                            expected_total=125000, recipient_name="مشتری", recipient_phone="09123456789")

    @staticmethod
    def _worker(barrier, action):
        # Django connections are thread-local. Never share the main thread's
        # connection or uncommitted ORM objects with another worker.
        connections.close_all()
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SET statement_timeout = '10000ms'")
                cursor.execute("SET lock_timeout = '8000ms'")
            barrier.wait(timeout=5)
            try:
                result = action()
                return ("ok", str(result.pk))
            except ShopError as error:
                return ("shop_error", error.code)
        finally:
            connections.close_all()

    def _parallel(self, first, second):
        barrier = threading.Barrier(2)
        pool = ThreadPoolExecutor(max_workers=2)
        try:
            futures = [pool.submit(self._worker, barrier, action) for action in (first, second)]
            return [future.result(timeout=20) for future in futures]
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

    def test_two_customers_compete_for_last_unit_and_exactly_one_reserves(self):
        results = self._parallel(lambda: self._order(self.customer_ids[0]), lambda: self._order(self.customer_ids[1]))
        self.assertEqual(sum(result[0] == "ok" for result in results), 1, results)
        self.assertEqual(sum(result == ("shop_error", "unavailable") for result in results), 1, results)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 0)
        self.assertEqual(self.inventory.version, 1)
        self.assertEqual(ShopOrder.objects.count(), 1)
        self.assertEqual(ShopOrder.objects.get().lines.get().quantity, 1)

    def test_two_adjustments_with_same_version_allow_one_audit_and_one_winner(self):
        def adjust(quantity):
            return adjust_inventory(actor=get_user_model().objects.get(pk=self.operator.pk), product_id=self.product.pk,
                                    quantity=quantity, expected_version=0, reason="شمارش واقعی هم‌زمان")
        results = self._parallel(lambda: adjust(5), lambda: adjust(8))
        self.assertEqual(sum(result[0] == "ok" for result in results), 1, results)
        self.assertEqual(sum(result == ("shop_error", "stock_changed") for result in results), 1, results)
        self.inventory.refresh_from_db()
        self.assertIn(self.inventory.quantity, (5, 8))
        self.assertEqual(self.inventory.version, 1)
        audit = ShopInventoryAudit.objects.get()
        self.assertEqual(audit.before, 1)
        self.assertEqual(audit.after, self.inventory.quantity)

    @override_settings(SHOP_PAYMENT_BACKEND="main.tests.test_shop_concurrency.BlockingGateway")
    def test_concurrent_callbacks_have_one_verification_and_one_paid_transition(self):
        order = self._order(self.customer_ids[0])
        start_payment(order=order, callback_url="https://www.zadconcept.ir/payment/verify/")
        payment = order.payments.get()
        BlockingGateway.entered = threading.Event()
        BlockingGateway.release = threading.Event()
        BlockingGateway.calls = 0
        barrier = threading.Barrier(2)
        pool = ThreadPoolExecutor(max_workers=2)
        futures = []
        try:
            futures = [pool.submit(self._worker, barrier, lambda: verify_payment(authority=payment.authority, callback_status="OK"))
                       for _ in range(2)]
            self.assertTrue(BlockingGateway.entered.wait(timeout=5), "No callback reached the authenticated provider verification")
            completed, _ = wait(futures, timeout=5, return_when=FIRST_COMPLETED)
            self.assertEqual(len(completed), 1, "The second callback must return pending while the first holds the verification lease")
            self.assertEqual(next(iter(completed)).result(), ("shop_error", "payment_pending"))
            BlockingGateway.release.set()
            results = [future.result(timeout=15) for future in futures]
        finally:
            BlockingGateway.release.set()
            pool.shutdown(wait=True, cancel_futures=True)
        self.assertEqual(sum(result[0] == "ok" for result in results), 1, results)
        self.assertEqual(BlockingGateway.calls, 1)
        order.refresh_from_db()
        payment.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(order.status, "paid")
        self.assertEqual(order.total_toman, 125000)
        self.assertEqual(payment.status, "paid")
        self.assertEqual(payment.amount_rial, 1250000)
        self.assertTrue(payment.reference)
        self.assertEqual(ShopPayment.objects.filter(status="paid").count(), 1)
        self.assertEqual(self.inventory.quantity, 0)
        self.assertEqual(self.inventory.version, 1)
        verify_payment(authority=payment.authority)
        self.assertEqual(BlockingGateway.calls, 1)
