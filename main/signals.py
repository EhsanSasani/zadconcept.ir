from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Product, ProductImage, Tag, WEDDING_LEGACY_TAG_SLUGS


@receiver(m2m_changed, sender=Product.tags.through)
def validate_and_touch_product_tags(
    sender,
    instance,
    action,
    reverse,
    pk_set,
    **kwargs,
):
    if action == "pre_add" and pk_set:
        if reverse:
            products = Product.objects.filter(pk__in=pk_set)
            if products.filter(catalog_scope=Product.CatalogScope.WEDDING).exists():
                raise ValidationError(
                    "محصول عروسی نمی‌تواند برچسب عمومی یا ارسال روز داشته باشد."
                )
            if (
                isinstance(instance, Tag)
                and instance.slug in WEDDING_LEGACY_TAG_SLUGS
                and products.filter(catalog_scope=Product.CatalogScope.GENERAL).exists()
            ):
                raise ValidationError(
                    "برچسب‌های قدیمی عروسی برای محصولات عمومی محافظت شده‌اند."
                )
        else:
            if instance.catalog_scope == Product.CatalogScope.WEDDING:
                raise ValidationError(
                    "محصول عروسی نمی‌تواند برچسب عمومی یا ارسال روز داشته باشد."
                )
            if Tag.objects.filter(
                pk__in=pk_set,
                slug__in=WEDDING_LEGACY_TAG_SLUGS,
            ).exists():
                raise ValidationError(
                    "برچسب‌های قدیمی عروسی برای محصولات عمومی محافظت شده‌اند."
                )

    if action not in {"post_add", "post_remove", "post_clear"}:
        return

    if reverse:
        if pk_set:
            Product.objects.filter(pk__in=pk_set).update(updated_at=timezone.now())
    elif instance.pk:
        Product.objects.filter(pk=instance.pk).update(updated_at=timezone.now())


@receiver(post_save, sender=ProductImage)
@receiver(post_delete, sender=ProductImage)
def touch_product_when_gallery_changes(sender, instance, **kwargs):
    if instance.product_id:
        Product.objects.filter(pk=instance.product_id).update(updated_at=timezone.now())
