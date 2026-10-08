from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from .image_pipeline import create_responsive_image_variants, normalize_new_model_images

from .models import (
    Product,
    ProductImage,
    StudioProduct,
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


@receiver(pre_delete, dispatch_uid="main.remember_deleted_telegram_product")
def remember_deleted_telegram_product(sender, instance, using, **kwargs):
    # Includes Product proxies and bulk admin deletion. Keep the message cursor
    # so Telegram retries or later price edits cannot recreate a deleted item.
    if isinstance(instance, Product):
        record = StudioProduct.objects.using(using).filter(product_id=instance.pk).first()
        if record:
            if not record.image and instance.cover_image:
                record.image = instance.cover_image.name
            if record.status == StudioProduct.Status.AVAILABLE:
                record.status = StudioProduct.Status.CANCELLED
            record.notes = (record.notes + "\nحذف از کاتالوگ ارسال روز").strip()
            record.save(update_fields=["image", "status", "notes", "updated_at"])
            from .studio_delivery import queue_retirement
            queue_retirement(record)
        from .models import TelegramSameDayPost
        TelegramSameDayPost.objects.using(using).filter(product_id=instance.pk).update(
            deleted_at=timezone.now(), source_photo={}, last_error="admin_deleted",
        )


@receiver(pre_save, sender=StudioProduct, dispatch_uid="main.snapshot_studio_admin_notification")
def snapshot_studio_admin_notification(sender, instance, raw=False, using=None, **kwargs):
    from .studio_admin_notifications import admin_notifications_enabled
    if raw or not instance.pk or not admin_notifications_enabled():
        instance._studio_notify_previous = None
        return
    previous = StudioProduct.objects.using(using).filter(pk=instance.pk)
    # Service/admin callers already hold the transaction. Keep concurrent
    # ledger updates serialized without requiring a lock in autocommit saves.
    if transaction.get_connection(using).in_atomic_block:
        previous = previous.select_for_update()
    instance._studio_notify_previous = previous.values("price", "status", "source").first()


@receiver(post_save, sender=StudioProduct, dispatch_uid="main.queue_studio_admin_notification")
def queue_studio_admin_notification(sender, instance, created=False, raw=False, using=None, **kwargs):
    from .studio_admin_notifications import admin_notifications_enabled
    if raw or not admin_notifications_enabled():
        return
    # update_fields may leave unsaved price/status values on the instance. A
    # notification must describe the persisted row, never those dirty values.
    persisted = StudioProduct.objects.using(using).filter(pk=instance.pk).first()
    if persisted is None or persisted.source not in {
        StudioProduct.Source.PORTAL,
        StudioProduct.Source.DASHBOARD,
        StudioProduct.Source.ADMIN,
    }:
        return

    from .models import StudioAdminNotification
    from .studio_admin_notifications import queue_admin_notification

    if created:
        queue_admin_notification(persisted, StudioAdminNotification.Event.CREATED)
        return

    previous = getattr(instance, "_studio_notify_previous", None)
    if not previous:
        return
    if previous["status"] != persisted.status:
        event = (
            StudioAdminNotification.Event.DELETED
            if persisted.status == StudioProduct.Status.DELETED
            else StudioAdminNotification.Event.STATUS
        )
        queue_admin_notification(persisted, event)
    elif previous["price"] != persisted.price:
        queue_admin_notification(persisted, StudioAdminNotification.Event.PRICE)


@receiver(post_save, dispatch_uid="main.sync_studio_public_projection")
def sync_studio_public_projection(sender, instance, raw=False, using=None, **kwargs):
    # SameDayFlower is the Django Admin proxy: Django sends its model as sender,
    # so listening only to Product silently misses actual catalog edits.
    if raw or sender._meta.concrete_model is not Product:
        return
    if not StudioProduct.objects.using(using).filter(product_id=instance.pk).exists():
        return
    with transaction.atomic(using=using):
        # Match the public-row-before-ledger lock order used by delivery/status
        # services. Read stored values, including for partial/proxy saves.
        public = Product.objects.using(using).select_for_update().filter(pk=instance.pk).first()
        if public is None:
            return
        record = StudioProduct.objects.using(using).select_for_update().filter(product_id=public.pk).first()
        if record is None:
            return
        if record.status == StudioProduct.Status.DELETED:
            # A catalog save cannot restore a deleted ledger entry or mutate
            # its retained photo, price and deletion audit.
            Product.objects.using(using).filter(pk=public.pk).update(
                status=Product.Status.WITHDRAWN,
                stock_status=Product.StockStatus.OUT_OF_STOCK,
                publish_status=Product.PublishStatus.DRAFT,
            )
            return
        changes = []
        if record.status in {StudioProduct.Status.SOLD, StudioProduct.Status.WITHDRAWN,
                             StudioProduct.Status.CANCELLED} and public.status == Product.Status.AVAILABLE:
            # Reopening requires the sales command, which also reconciles the
            # retirement job and the Telegram identity. A catalog save cannot do it.
            Product.objects.using(using).filter(pk=public.pk).update(
                status=Product.Status.SOLD if record.status == StudioProduct.Status.SOLD else Product.Status.WITHDRAWN,
                stock_status=Product.StockStatus.OUT_OF_STOCK,
            )
        if public.price is not None and public.price > 0 and record.price != public.price:
            record.price = public.price
            changes.append("price")
        if public.cover_image and record.image.name != public.cover_image.name:
            record.image = public.cover_image.name
            changes.append("image")
        if record.status == StudioProduct.Status.AVAILABLE:
            if public.status == Product.Status.SOLD:
                record.status, record.sold_at = StudioProduct.Status.SOLD, timezone.now()
                changes.extend(("status", "sold_at"))
            elif public.status == Product.Status.WITHDRAWN:
                record.status, record.withdrawn_at = StudioProduct.Status.WITHDRAWN, timezone.now()
                changes.extend(("status", "withdrawn_at"))
        if changes:
            # save() emits one persisted-state notification (status wins over
            # price), preserves the source, and never creates a publish job.
            record.save(using=using, update_fields=[*changes, "updated_at"])
        if "status" in changes:
            from .studio_delivery import queue_retirement
            queue_retirement(record)
