from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Product, ProductImage


@receiver(m2m_changed, sender=Product.tags.through)
def touch_product_when_tags_change(sender, instance, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"} and instance.pk:
        Product.objects.filter(pk=instance.pk).update(updated_at=timezone.now())


@receiver(post_save, sender=ProductImage)
@receiver(post_delete, sender=ProductImage)
def touch_product_when_gallery_changes(sender, instance, **kwargs):
    if instance.product_id:
        Product.objects.filter(pk=instance.product_id).update(updated_at=timezone.now())
