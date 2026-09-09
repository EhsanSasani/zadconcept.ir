from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .image_pipeline import create_responsive_image_variants, normalize_new_model_images

from .models import (
    Product,
    ProductImage,
    Story,
    StoryClip,
    Tag,
    WEDDING_LEGACY_TAG_SLUGS,
)


@receiver(pre_save, dispatch_uid="main.normalize_new_image_uploads")
def normalize_image_uploads(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or sender._meta.app_label != "main":
        return
    normalize_new_model_images(instance, update_fields=update_fields)


@receiver(post_save, dispatch_uid="main.create_catalog_image_variants")
def build_catalog_image_variants(sender, instance, raw=False, using=None, **kwargs):
    concrete_model = sender._meta.concrete_model
    if raw or concrete_model not in (Product, ProductImage):
        return
    new_fields = getattr(instance, "_zad_new_image_fields", set())
    instance._zad_new_image_fields = set()
    field_name = "cover_image" if concrete_model is Product else "image"
    if field_name not in new_fields:
        return
    image = getattr(instance, field_name)
    stored_name, storage, object_pk = image.name, image.storage, instance.pk

    def build_after_commit():
        # An upload replaced/deleted again in the transaction needs no variants.
        if concrete_model._base_manager.using(using).filter(
            pk=object_pk, **{field_name: stored_name}
        ).exists():
            create_responsive_image_variants(storage, stored_name)

    transaction.on_commit(build_after_commit, using=using)


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
                    "محصول عروسی نمی‌تواند برچسب عمومی داشته باشد."
                )
            if (
                isinstance(instance, Tag)
                and instance.slug in WEDDING_LEGACY_TAG_SLUGS
                and products.filter(
                    catalog_scope__in=(
                        Product.CatalogScope.GENERAL,
                        Product.CatalogScope.SAME_DAY,
                    )
                ).exists()
            ):
                raise ValidationError(
                    "برچسب‌های قدیمی عروسی برای محصولات عمومی محافظت شده‌اند."
                )
        else:
            if instance.catalog_scope == Product.CatalogScope.WEDDING:
                raise ValidationError(
                    "محصول عروسی نمی‌تواند برچسب عمومی داشته باشد."
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


@receiver(post_delete, dispatch_uid="main.delete_story_clip_media")
def delete_story_clip_media(sender, instance, using=None, **kwargs):
    if sender._meta.concrete_model is not StoryClip:
        return
    stored_files = []
    for field_name in ("source_video", "optimized_video", "poster_image", "image"):
        field_file = getattr(instance, field_name, None)
        if field_file and field_file.name:
            stored_files.append((field_file.storage, field_file.name))

    if not stored_files:
        return

    def delete_files_after_commit():
        for storage, stored_name in stored_files:
            references = Q()
            for field_name in ("source_video", "optimized_video", "poster_image", "image"):
                references |= Q(**{field_name: stored_name})
            if StoryClip.objects.using(using).filter(references).exists():
                continue
            try:
                storage.delete(stored_name)
            except OSError:
                pass

    transaction.on_commit(delete_files_after_commit, using=using)
