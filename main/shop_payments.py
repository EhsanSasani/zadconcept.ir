"""Provider boundary. Disabled until an actual merchant adapter is configured.

Adapters must perform authenticated server-to-server verification and return
the amount, merchant, order and authority obtained from the provider, not from
the browser's callback. A browser success flag is never proof of payment.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import ShopOrder, ShopPayment
from .shop_service import ShopError, _release_locked


@dataclass(frozen=True)
class GatewayRequest:
    authority: str
    payment_url: str


@dataclass(frozen=True)
class GatewayVerification:
    outcome: str  # paid, rejected (definitive), or pending (ambiguous)
    authority: str
    order_id: str
    amount_rial: int
    reference: str = ""
    merchant_id: str = ""


def payment_enabled():
    return bool(getattr(settings, "SHOP_PAYMENT_ENABLED", False) and getattr(settings, "SHOP_PAYMENT_BACKEND", ""))


def get_gateway():
    if not payment_enabled():
        raise ShopError("payment_disabled", "پرداخت آنلاین هنوز فعال نشده است؛ سبد شما محفوظ می‌ماند.")
    backend = settings.SHOP_PAYMENT_BACKEND
    if getattr(settings, "IS_PRODUCTION", False) and backend.startswith(("main.tests.", "tests.")):
        raise ShopError("payment_unavailable", "درگاه آزمایشی برای پرداخت واقعی قابل استفاده نیست.")
    try:
        gateway = import_string(backend)()
        if getattr(settings, "IS_PRODUCTION", False) and getattr(gateway, "test_only", False):
            raise ValueError
        if not gateway.name or len(gateway.name) > 100 or not gateway.merchant_id or not gateway.allowed_hosts:
            raise ValueError
        return gateway
    except Exception:
        raise ShopError("payment_unavailable", "اتصال به درگاه در دسترس نیست؛ لطفاً بعداً دوباره بررسی کنید.") from None


def toman_to_rial(amount):
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ShopError("invalid_amount", "مبلغ پرداخت معتبر نیست.")
    return amount * 10


def _safe_https(url, allowed_hosts=None):
    try:
        parsed = urlsplit(url)
        return bool(
            parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
            and not parsed.fragment and parsed.port in (None, 443)
            and (allowed_hosts is None or parsed.hostname in allowed_hosts)
        )
    except (TypeError, ValueError):
        return False


def _review(payment_id, error):
    ShopPayment.objects.filter(pk=payment_id).exclude(status=ShopPayment.Status.PAID).update(
        status=ShopPayment.Status.REVIEW, last_error=error, verify_token=None, verify_started_at=None,
    )


def start_payment(*, order, callback_url):
    gateway = get_gateway()
    if not _safe_https(callback_url):
        raise ShopError("invalid_callback", "نشانی بازگشت پرداخت باید امن باشد.")
    with transaction.atomic():
        order = ShopOrder.objects.select_for_update().get(pk=order.pk)
        if order.status != ShopOrder.Status.PENDING or order.released_at:
            raise ShopError("invalid_state", "این سفارش برای پرداخت آماده نیست.")
        blocking = order.payments.exclude(status=ShopPayment.Status.FAILED).first()
        if blocking:
            if blocking.status == ShopPayment.Status.PENDING and blocking.payment_url:
                return blocking.payment_url
            raise ShopError("payment_pending", "نتیجهٔ درخواست قبلی در حال بررسی است؛ پرداخت تازه‌ای ایجاد نشد.")
        if order.reserved_until <= timezone.now():
            raise ShopError("order_expired", "زمان رزرو سفارش تمام شده است؛ موجودی و قیمت سبد را دوباره بررسی کنید.")
        payment = ShopPayment.objects.create(order=order, provider=gateway.name, amount_rial=toman_to_rial(order.total_toman))
    try:
        result = gateway.request_payment(
            order_id=str(order.pk), amount_rial=payment.amount_rial,
            callback_url=callback_url, idempotency_key=str(payment.pk),
        )
        if (not isinstance(result, GatewayRequest) or not isinstance(result.authority, str)
            or not 1 <= len(result.authority) <= 128 or not _safe_https(result.payment_url, gateway.allowed_hosts)):
            raise ValueError("invalid_gateway_response")
        with transaction.atomic():
            ShopOrder.objects.select_for_update().get(pk=order.pk)
            attempt = ShopPayment.objects.select_for_update().get(pk=payment.pk)
            attempt.authority = result.authority
            attempt.payment_url = result.payment_url
            attempt.status = ShopPayment.Status.PENDING
            attempt.save(update_fields=["authority", "payment_url", "status"])
        return result.payment_url
    except Exception:
        # The provider might have accepted a request before the connection failed.
        # Keep reserved stock and block another charge until reconciliation.
        _review(payment.pk, "request_uncertain")
        raise ShopError("payment_pending", "نتیجهٔ ارتباط با درگاه قطعی نیست؛ سفارش محفوظ است و باید بررسی شود.") from None


def verify_payment(*, authority, callback_status=""):
    """callback_status is deliberately ignored; only authenticated verification settles."""
    if not isinstance(authority, str) or not 1 <= len(authority) <= 128:
        raise ShopError("invalid_payment", "شناسهٔ پرداخت معتبر نیست.")
    try:
        initial = ShopPayment.objects.get(authority=authority)
    except ShopPayment.DoesNotExist:
        raise ShopError("invalid_payment", "پرداخت پیدا نشد.") from None
    gateway = get_gateway()
    now = timezone.now()
    with transaction.atomic():
        order = ShopOrder.objects.select_for_update().get(pk=initial.order_id)
        payment = ShopPayment.objects.select_for_update().get(pk=initial.pk)
        if payment.status == ShopPayment.Status.PAID:
            return order
        if payment.provider != gateway.name:
            raise ShopError("provider_changed", "تطبیق این تراکنش به بررسی پشتیبانی نیاز دارد.")
        if payment.verify_token and payment.verify_started_at and payment.verify_started_at > now - timedelta(minutes=2):
            raise ShopError("payment_pending", "تأیید این پرداخت در حال انجام است.")
        token = uuid.uuid4()
        payment.verify_token, payment.verify_started_at = token, now
        payment.save(update_fields=["verify_token", "verify_started_at"])
    try:
        result = gateway.verify_payment(authority=authority, order_id=str(order.pk), amount_rial=payment.amount_rial)
    except Exception:
        ShopPayment.objects.filter(pk=payment.pk, verify_token=token).update(
            status=ShopPayment.Status.REVIEW, last_error="verification_uncertain", verify_token=None, verify_started_at=None,
        )
        raise ShopError("payment_pending", "نتیجهٔ پرداخت هنوز قطعی نیست؛ بررسی دوباره انجام خواهد شد.") from None
    valid = (
        isinstance(result, GatewayVerification) and result.outcome in ("paid", "rejected", "pending")
        and result.authority == authority and result.order_id == str(order.pk)
        and type(result.amount_rial) is int and result.amount_rial == payment.amount_rial
        and result.merchant_id == gateway.merchant_id
        and (result.outcome != "paid" or isinstance(result.reference, str) and 1 <= len(result.reference) <= 128)
    )
    if not valid:
        ShopPayment.objects.filter(pk=payment.pk, verify_token=token).update(
            status=ShopPayment.Status.REVIEW, last_error="verification_mismatch", verify_token=None, verify_started_at=None,
        )
        raise ShopError("verification_mismatch", "اطلاعات تأیید درگاه با سفارش تطابق ندارد؛ پشتیبانی باید بررسی کند.")
    try:
        with transaction.atomic():
            order = ShopOrder.objects.select_for_update().get(pk=payment.order_id)
            payment = ShopPayment.objects.select_for_update().get(pk=payment.pk)
            if payment.status == ShopPayment.Status.PAID:
                return order
            if payment.verify_token != token:
                raise ShopError("payment_pending", "تأیید پرداخت دیگری در حال انجام است.")
            payment.verify_token, payment.verify_started_at = None, None
            if result.outcome == "paid":
                payment.reference, payment.verified_at = result.reference, timezone.now()
                if order.released_at or order.status != ShopOrder.Status.PENDING:
                    payment.status, payment.last_error = ShopPayment.Status.REVIEW, "late_payment_review"
                    if order.status != ShopOrder.Status.PAID:
                        order.status = ShopOrder.Status.REVIEW
                        order.save(update_fields=["status"])
                else:
                    payment.status, payment.last_error = ShopPayment.Status.PAID, ""
                    order.status, order.paid_at = ShopOrder.Status.PAID, timezone.now()
                    order.save(update_fields=["status", "paid_at"])
            elif result.outcome == "rejected":
                payment.status, payment.last_error = ShopPayment.Status.FAILED, "provider_rejected"
                if order.status == ShopOrder.Status.PENDING:
                    _release_locked(order)
            else:
                payment.status, payment.last_error = ShopPayment.Status.REVIEW, "provider_pending"
            payment.save()
        return order
    except IntegrityError:
        ShopPayment.objects.filter(pk=payment.pk, verify_token=token).update(
            status=ShopPayment.Status.REVIEW, last_error="transaction_conflict", verify_token=None, verify_started_at=None,
        )
        raise ShopError("transaction_conflict", "شناسهٔ تراکنش تکراری است؛ پرداخت نیاز به بررسی دارد.") from None
