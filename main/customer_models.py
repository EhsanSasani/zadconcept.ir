"""Customer identities and durable one-time login challenges, separate from staff roles."""

from django.conf import settings
from django.db import models


class CustomerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name="customer_profile")
    phone = models.CharField("شماره موبایل", max_length=16, unique=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "مشتری فروشگاه"
        verbose_name_plural = "مشتری‌های فروشگاه"


class CustomerLoginRate(models.Model):
    # Keyed digests avoid storing the requesting IP address in this table.
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
