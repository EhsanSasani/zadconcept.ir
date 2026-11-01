"""Server-authoritative cart, stock reservations and order transitions."""

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, F, OuterRef
from django.utils import timezone

from .models import Product, ShopConfiguration, ShopInventory, ShopInventoryAudit, ShopOrder, ShopOrderLine, ShopPayment

MAX_CART_LINES = 30
MAX_LINE_QUANTITY = 99


class ShopError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class CartLine:
    product: Product
    quantity: int
    unit_price_toman: int
    subtotal_toman: int
    stock: int


@dataclass(frozen=True)
class CartSnapshot:
    lines: list
    total_toman: int
    errors: list

    @property
    def is_valid(self):
        return bool(self.lines) and not self.errors


def _integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError
    if isinstance(value, str) and not re.fullmatch(r"[0-9]{1,18}", value):
        raise ValueError
    return int(value)


def normalize_cart(cart):
    if not isinstance(cart, dict) or not cart or len(cart) > MAX_CART_LINES:
        raise ShopError("invalid_cart", "سبد خرید خالی است یا تعداد ردیف‌های آن معتبر نیست.")
    normalized = {}
    try:
        for key, value in cart.items():
            product_id, quantity = _integer(key), _integer(value)
            if product_id <= 0 or not 1 <= quantity <= MAX_LINE_QUANTITY or product_id in normalized:
                raise ValueError
            normalized[product_id] = quantity
    except (ValueError, OverflowError):
        raise ShopError("invalid_quantity", "تعداد محصول باید بین ۱ تا ۹۹ باشد.") from None
    return normalized


def cart_snapshot(cart):
    if not cart:
        return CartSnapshot([], 0, [])
    try:
        normalized = normalize_cart(cart)
    except ShopError as error:
        return CartSnapshot([], 0, [str(error)])
    products = {
        product.pk: product
        for product in Product.objects.for_shop().published()
        .filter(pk__in=normalized).select_related("category", "shop_inventory")
    }
    lines, errors, total = [], [], 0
    for product_id, quantity in normalized.items():
        product = products.get(product_id)
        if product is None:
            errors.append("یکی از محصولات سبد دیگر در فروشگاه عرضه نمی‌شود؛ آن را از سبد حذف کنید.")
            continue
        try:
            stock = product.shop_inventory.quantity
        except ShopInventory.DoesNotExist:
            stock = 0
        if not product.shop_purchasable or quantity > stock:
            errors.append(f"موجودی «{product.display_name}» برای تعداد انتخاب‌شده کافی نیست.")
        if not product.has_price or product.price <= 0:
            errors.append(f"قیمت «{product.display_name}» برای خرید آنلاین تعیین نشده است.")
            continue
        unit_price = int(product.price)
        subtotal = unit_price * quantity
        lines.append(CartLine(product, quantity, unit_price, subtotal, stock))
        total += subtotal
    return CartSnapshot(lines, total, errors)


def _require_customer(customer):
    from .customer_auth import is_customer
    if not is_customer(customer):
        raise ShopError("customer_required", "برای ثبت سفارش، ابتدا وارد حساب مشتری شوید.")


def shop_configuration():
    """Public reads use safe defaults without creating database state."""
    return ShopConfiguration.objects.filter(pk=1).first() or ShopConfiguration()


def fulfillment_quote(mode, *, configuration=None):
    configuration = configuration or shop_configuration()
    if mode == "pickup" and configuration.pickup_enabled:
        return 0
    if (mode == "delivery" and configuration.delivery_enabled and type(configuration.delivery_fee_toman) is int
        and 0 <= configuration.delivery_fee_toman <= 1000000000000):
        return configuration.delivery_fee_toman
    raise ShopError("delivery_unavailable", "روش دریافت انتخاب‌شده فعلاً در دسترس نیست؛ روش دیگری را انتخاب کنید.")


@transaction.atomic
def adjust_inventory(*, actor, product_id, quantity, expected_version, reason):
    if not actor.is_authenticated or not actor.is_active or not actor.has_perm("main.manage_shop"):
        raise ShopError("forbidden", "اجازهٔ مدیریت موجودی فروشگاه را ندارید.")
    try:
        quantity, expected_version = _integer(quantity), _integer(expected_version)
        if not 0 <= quantity <= 1000000 or expected_version < 0:
            raise ValueError
    except (ValueError, OverflowError):
        raise ShopError("invalid_quantity", "تعداد موجودی معتبر نیست.") from None
    reason = str(reason or "").strip()
    if not reason or len(reason) > 500:
        raise ShopError("reason_required", "دلیل تغییر موجودی را تا ۵۰۰ نویسه وارد کنید.")
    try:
        product = Product.objects.select_for_update().get(pk=product_id, catalog_scope="shop")
    except (Product.DoesNotExist, ValueError):
        raise ShopError("not_shop", "این محصول متعلق به فروشگاه نیست.") from None
    inventory, _ = ShopInventory.objects.select_for_update().get_or_create(product=product)
    if inventory.version != expected_version:
        raise ShopError("stock_changed", "موجودی تغییر کرده است؛ صفحه را تازه کنید و دوباره بررسی کنید.")
    before = inventory.quantity
    if ShopInventory.objects.filter(pk=inventory.pk, version=expected_version).update(
        quantity=quantity, version=F("version") + 1, updated_at=timezone.now(),
    ) != 1:
        raise ShopError("stock_changed", "موجودی تغییر کرده است؛ صفحه را تازه کنید و دوباره بررسی کنید.")
    ShopInventoryAudit.objects.create(product=product, actor=actor, before=before, after=quantity, reason=reason)
    inventory.refresh_from_db()
    return inventory


def _existing_order(customer, nonce, cart, expected_total, fulfillment, recipient_address, recipient_city,
                    recipient_name, recipient_phone, customer_note):
    existing = ShopOrder.objects.filter(nonce=nonce).first()
    if existing is None:
        return None
    if existing.customer_id != customer.pk:
        raise ShopError("invalid_order", "شناسهٔ درخواست معتبر نیست.")
    line_cart = dict(existing.lines.values_list("product_id", "quantity"))
    if (line_cart != cart or existing.total_toman != expected_total or existing.fulfillment != fulfillment
        or existing.recipient_address != recipient_address or existing.recipient_city != recipient_city
        or existing.recipient_name != recipient_name or existing.recipient_phone != recipient_phone
        or existing.customer_note != customer_note):
        raise ShopError("request_changed", "سبد با درخواست قبلی تفاوت دارد؛ صفحهٔ پرداخت را تازه کنید.")
    return existing


def create_order(*, customer, cart, nonce, expected_total, recipient_name, recipient_phone,
                 customer_note="", fulfillment="pickup", recipient_address="", recipient_city="مشهد"):
    _require_customer(customer)
    normalized = normalize_cart(cart)
    try:
        nonce = uuid.UUID(str(nonce))
        expected_total = _integer(expected_total)
    except (ValueError, TypeError, AttributeError):
        raise ShopError("invalid_order", "اطلاعات درخواست سفارش معتبر نیست.") from None
    recipient_name = str(recipient_name or "").strip()
    recipient_phone = str(recipient_phone or "").strip()
    customer_note = str(customer_note or "").strip()
    recipient_address = str(recipient_address or "").strip()
    recipient_city = str(recipient_city or "").strip()
    from .customer_auth import normalize_phone
    try:
        recipient_phone = normalize_phone(recipient_phone)
    except ValidationError:
        raise ShopError("invalid_recipient", "نام و شمارهٔ همراه تحویل‌گیرنده را بررسی کنید.") from None
    if not 1 <= len(recipient_name) <= 120:
        raise ShopError("invalid_recipient", "نام و شمارهٔ همراه تحویل‌گیرنده را بررسی کنید.")
    if len(customer_note) > 500 or fulfillment not in ("pickup", "delivery"):
        raise ShopError("invalid_fulfillment", "روش دریافت و یادداشت سفارش را بررسی کنید.")
    if fulfillment == "delivery" and (recipient_city != "مشهد" or not 10 <= len(recipient_address) <= 1000):
        raise ShopError("invalid_address", "ارسال فقط در مشهد انجام می‌شود؛ نشانی کامل مشهد را وارد کنید.")
    if fulfillment == "pickup":
        recipient_address, recipient_city = "", ""
    existing = _existing_order(customer, nonce, normalized, expected_total, fulfillment, recipient_address, recipient_city,
                               recipient_name, recipient_phone, customer_note)
    if existing:
        return existing
    # Never create a misleading payable order or reserve stock with no gateway.
    from .shop_payments import get_gateway
    get_gateway()
    try:
        with transaction.atomic():
            existing = _existing_order(customer, nonce, normalized, expected_total, fulfillment, recipient_address, recipient_city,
                                       recipient_name, recipient_phone, customer_note)
            if existing:
                return existing
            configuration, _ = ShopConfiguration.objects.select_for_update().get_or_create(pk=1)
            shipping_fee = fulfillment_quote(fulfillment, configuration=configuration)
            products = list(Product.objects.select_for_update().filter(pk__in=sorted(normalized)).order_by("pk"))
            inventories = {
                stock.product_id: stock
                for stock in ShopInventory.objects.select_for_update().filter(product_id__in=normalized).order_by("product_id")
            }
            if len(products) != len(normalized):
                raise ShopError("unavailable", "یکی از محصولات دیگر قابل خرید نیست.")
            total, snapshots = 0, []
            for product in products:
                inventory = inventories.get(product.pk)
                quantity = normalized[product.pk]
                if (not product.is_shop or not product.is_published or not product.category.is_active
                    or product.status != Product.Status.AVAILABLE or product.stock_status != Product.StockStatus.IN_STOCK
                    or not product.has_price or product.price <= 0 or not inventory or inventory.quantity < quantity):
                    raise ShopError("unavailable", "قیمت یا موجودی یکی از محصولات تغییر کرده است؛ سبد را بررسی کنید.")
                total += int(product.price) * quantity
                snapshots.append((product, quantity, int(product.price)))
            final_total = total + shipping_fee
            if total <= 0 or final_total != expected_total:
                raise ShopError("price_changed", "قیمت سبد تغییر کرده است؛ مبلغ جدید را بررسی و دوباره تأیید کنید.")
            order = ShopOrder.objects.create(
                customer=customer, nonce=nonce, total_toman=final_total, items_total_toman=total,
                shipping_fee_toman=shipping_fee, recipient_name=recipient_name,
                recipient_phone=recipient_phone, customer_note=customer_note, fulfillment=fulfillment,
                recipient_address=recipient_address, recipient_city=recipient_city,
                reserved_until=timezone.now() + timedelta(minutes=20),
            )
            for product, quantity, unit_price in snapshots:
                updated = ShopInventory.objects.filter(product=product, quantity__gte=quantity).update(
                    quantity=F("quantity") - quantity, version=F("version") + 1,
                )
                if updated != 1:
                    raise ShopError("stock_changed", "موجودی تغییر کرد؛ سبد خرید را دوباره بررسی کنید.")
                ShopOrderLine.objects.create(order=order, product=product, product_name=product.display_name,
                                             unit_price_toman=unit_price, quantity=quantity)
            return order
    except IntegrityError:
        existing = _existing_order(customer, nonce, normalized, expected_total, fulfillment, recipient_address, recipient_city,
                                   recipient_name, recipient_phone, customer_note)
        if existing:
            return existing
        raise


def _release_locked(order):
    """Caller locks the order; exactly one release can put reserved units back."""
    if order.released_at or order.status == ShopOrder.Status.PAID:
        return False
    for line in order.lines.order_by("product_id"):
        ShopInventory.objects.filter(product_id=line.product_id).update(
            quantity=F("quantity") + line.quantity, version=F("version") + 1,
        )
    order.released_at = timezone.now()
    order.status = ShopOrder.Status.CANCELLED
    order.save(update_fields=["status", "released_at"])
    return True


def _ambiguous_payment(order):
    return order.payments.filter(status__in=[ShopPayment.Status.REQUESTING, ShopPayment.Status.PENDING, ShopPayment.Status.REVIEW]).exists()


@transaction.atomic
def cancel_order(*, customer, order_id):
    _require_customer(customer)
    try:
        order = ShopOrder.objects.select_for_update().get(pk=order_id, customer=customer)
    except (ShopOrder.DoesNotExist, ValueError):
        raise ShopError("not_found", "سفارش پیدا نشد.") from None
    if order.status == ShopOrder.Status.PAID:
        raise ShopError("already_paid", "سفارش پرداخت‌شده با این درخواست لغو نمی‌شود.")
    if _ambiguous_payment(order):
        raise ShopError("payment_pending", "نتیجهٔ پرداخت هنوز قطعی نیست؛ ابتدا وضعیت تراکنش باید بررسی شود.")
    _release_locked(order)
    return order


def expire_orders(*, now=None, limit=100):
    now = now or timezone.now()
    expired = 0
    ambiguous = ShopPayment.objects.filter(order_id=OuterRef("pk"), status__in=[
        ShopPayment.Status.REQUESTING, ShopPayment.Status.PENDING, ShopPayment.Status.REVIEW,
    ])
    ids = list(ShopOrder.objects.filter(status="pending", released_at__isnull=True, reserved_until__lte=now)
               .annotate(has_ambiguous_payment=Exists(ambiguous)).filter(has_ambiguous_payment=False)
               .order_by("reserved_until").values_list("pk", flat=True)[:limit])
    for order_id in ids:
        with transaction.atomic():
            order = ShopOrder.objects.select_for_update().get(pk=order_id)
            if order.status == ShopOrder.Status.PENDING and not order.released_at and not _ambiguous_payment(order):
                expired += int(_release_locked(order))
    return expired
