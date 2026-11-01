"""Separate shop inventory, immutable order snapshots and payment attempts."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ShopInventory(models.Model):
    product = models.OneToOneField("main.Product", on_delete=models.PROTECT, related_name="shop_inventory")
    quantity = models.PositiveIntegerField("تعداد قابل فروش", default=0)
    version = models.PositiveIntegerField(default=0, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "موجودی فروشگاه"
        verbose_name_plural = "موجودی فروشگاه"
        permissions = [("manage_shop", "مدیریت محصولات و موجودی فروشگاه")]
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=0), name="shop_inventory_nonnegative")]

    def clean(self):
        if self.product_id and self.product.catalog_scope != "shop":
            raise ValidationError({"product": "موجودی فروشگاه فقط برای محصولات بخش فروشگاه است."})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class ShopInventoryAudit(models.Model):
    product = models.ForeignKey("main.Product", on_delete=models.PROTECT, related_name="shop_stock_audits")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    before = models.PositiveIntegerField()
    after = models.PositiveIntegerField()
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-pk"]
        default_permissions = ("view",)


class ShopConfiguration(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    pickup_enabled = models.BooleanField("دریافت حضوری فعال", default=True)
    delivery_enabled = models.BooleanField("ارسال در مشهد فعال", default=False)
    delivery_fee_toman = models.PositiveBigIntegerField("هزینه ارسال مشهد (تومان)", null=True, blank=True, validators=[MaxValueValidator(1000000000000)])

    class Meta:
        verbose_name = "تنظیمات فروشگاه"
        verbose_name_plural = "تنظیمات فروشگاه"
        constraints = [
            models.CheckConstraint(condition=Q(pk=1), name="shop_config_singleton"),
            models.CheckConstraint(condition=Q(delivery_enabled=False) | Q(delivery_fee_toman__isnull=False), name="shop_delivery_fee_explicit"),
            models.CheckConstraint(condition=Q(pickup_enabled=True) | Q(delivery_enabled=True), name="shop_fulfillment_enabled"),
            models.CheckConstraint(condition=Q(delivery_fee_toman__isnull=True) | Q(delivery_fee_toman__lte=1000000000000), name="shop_delivery_fee_bounded"),
        ]

    def clean(self):
        if self.delivery_enabled and self.delivery_fee_toman is None:
            raise ValidationError({"delivery_fee_toman": "هزینهٔ ارسال را مشخص کنید؛ ارسال رایگان باید صریحاً صفر باشد."})
        if not self.pickup_enabled and not self.delivery_enabled:
            raise ValidationError("حداقل یک روش دریافت باید فعال باشد.")


class ShopOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار پرداخت"
        PAID = "paid", "پرداخت‌شده"
        CANCELLED = "cancelled", "لغوشده"
        REVIEW = "review", "نیازمند بررسی پرداخت"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shop_orders")
    nonce = models.UUIDField(unique=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    total_toman = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    items_total_toman = models.PositiveBigIntegerField(default=0)
    shipping_fee_toman = models.PositiveBigIntegerField(default=0)
    fulfillment = models.CharField(max_length=12, default="pickup", choices=[("pickup", "تحویل حضوری"), ("delivery", "ارسال در مشهد")])
    recipient_name = models.CharField(max_length=120)
    recipient_phone = models.CharField(max_length=16)
    customer_note = models.CharField(max_length=500, blank=True)
    recipient_address = models.CharField(max_length=1000, blank=True)
    recipient_city = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    reserved_until = models.DateTimeField(db_index=True)
    released_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(total_toman__gt=0), name="shop_order_positive_total"),
            models.CheckConstraint(condition=Q(fulfillment__in=["pickup", "delivery"]), name="shop_order_fulfillment_valid"),
            models.CheckConstraint(condition=Q(items_total_toman__gt=0), name="shop_order_items_positive"),
            models.CheckConstraint(condition=Q(total_toman=models.F("items_total_toman") + models.F("shipping_fee_toman")), name="shop_order_total_consistent"),
            models.CheckConstraint(condition=~Q(status="paid") | Q(paid_at__isnull=False, released_at__isnull=True), name="shop_order_paid_consistent"),
        ]


class ShopOrderLine(models.Model):
    order = models.ForeignKey(ShopOrder, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey("main.Product", on_delete=models.PROTECT, related_name="shop_order_lines")
    product_name = models.CharField(max_length=120)
    unit_price_toman = models.PositiveBigIntegerField()
    quantity = models.PositiveSmallIntegerField()

    @property
    def subtotal_toman(self):
        return self.unit_price_toman * self.quantity

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="shop_order_product_unique"),
            models.CheckConstraint(condition=Q(quantity__gte=1, quantity__lte=99), name="shop_line_quantity_valid"),
            models.CheckConstraint(condition=Q(unit_price_toman__gt=0), name="shop_line_price_positive"),
        ]


class ShopPayment(models.Model):
    class Status(models.TextChoices):
        REQUESTING = "requesting", "در حال درخواست درگاه"
        PENDING = "pending", "در انتظار نتیجه درگاه"
        PAID = "paid", "تأییدشده"
        FAILED = "failed", "ناموفق قطعی"
        REVIEW = "review", "نیازمند تطبیق"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(ShopOrder, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=100)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTING, db_index=True)
    authority = models.CharField(max_length=128, null=True, blank=True, unique=True)
    reference = models.CharField(max_length=128, null=True, blank=True, unique=True)
    amount_rial = models.PositiveBigIntegerField()
    payment_url = models.URLField(max_length=1000, blank=True)
    verify_token = models.UUIDField(null=True, blank=True, editable=False)
    verify_started_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount_rial__gt=0), name="shop_payment_amount_positive"),
            models.UniqueConstraint(fields=["order"], condition=Q(status="paid"), name="shop_one_paid_attempt"),
        ]
