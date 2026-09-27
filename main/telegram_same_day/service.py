"""Same-day sync. Row locks serialize edits, retries and SOLD per channel post."""
import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..image_pipeline import ImageUploadError, normalize_admin_image
from ..models import Category, Product, StudioProduct, TelegramBotUser, TelegramDiscussionMessage, TelegramSameDayPost
from .client import download_photo
from .price import PriceError, parse_price, parse_group_price

logger = logging.getLogger("main.telegram_same_day")


class SyncConfigurationError(Exception):
    pass


class InvalidSource(Exception):
    pass


def _post(chat_id, message_id):
    post, _ = TelegramSameDayPost.objects.get_or_create(
        telegram_chat_id=chat_id, telegram_message_id=message_id,
    )
    # Do not join the nullable Product FK: PostgreSQL cannot lock its outer join.
    return TelegramSameDayPost.objects.select_for_update().get(pk=post.pk)


def _category():
    category = Category.objects.for_general_catalog().filter(
        pk=settings.TELEGRAM_SAME_DAY_CATEGORY_ID,
        section=Category.Section.FLOWERS, is_active=True,
    ).first() if str(settings.TELEGRAM_SAME_DAY_CATEGORY_ID).isdigit() else None
    if not category or category.is_wedding_category:
        raise SyncConfigurationError("same_day_category_missing_or_invalid")
    return category


def _record_failure(post, reason, event="price parsing failed"):
    post.last_error = reason
    post.save()
    if post.product_id:
        Product.objects.filter(pk=post.product_id).update(
            publish_status=Product.PublishStatus.DRAFT, updated_at=timezone.now(),
        )
    logger.warning("%s chat_id=%s message_id=%s reason=%s",
                   event, post.telegram_chat_id, post.telegram_message_id, reason)
    return "price_parsing_failed"


def _sync_product(message, update_id, stored_files, *, direct_group=False):
    post = _post(message["chat"]["id"], message["message_id"])
    if post.deleted_at:
        return "admin_deleted_ignored"
    revision = message.get("edit_date", message.get("date", 0))
    if not revision:
        return "missing_date_ignored"
    if (revision, update_id) <= (post.revision_date, post.revision_update_id):
        logger.info("duplicate ignored chat_id=%s message_id=%s", post.telegram_chat_id, post.telegram_message_id)
        return "duplicate_ignored"
    from ..studio_ingestion import StudioInputError, resolve_metadata, sync_daily
    metadata = None
    studio_error = ""
    try:
        metadata = resolve_metadata(message.get("caption", ""), identity=(post.telegram_chat_id, post.telegram_message_id))
    except StudioInputError as error:
        studio_error = str(error)
        # Existing group messages without ledger metadata remain supported until
        # the explicit production cutover. New messages can be made strict.
        if settings.STUDIO_DAILY_REQUIRE_METADATA and not post.product_id:
            post.studio_error = studio_error
            post.save(update_fields=["studio_error", "updated_at"])
            return "studio_metadata_rejected"
    post.revision_date, post.revision_update_id = revision, update_id
    if direct_group and message.get("photo"):
        post.source_photo = {key: message[key] for key in
                             ("message_id", "chat", "date", "photo", "media_group_id", "caption") if key in message}
    if message.get("date"):
        post.telegram_created_at = datetime.fromtimestamp(message["date"], tz=dt_timezone.utc)
    try:
        price = (parse_group_price if direct_group else parse_price)(message.get("caption"))
    except PriceError as error:
        return _record_failure(post, str(error))
    if not message.get("photo") or message.get("media_group_id"):
        return _record_failure(post, "single_photo_required", "product media rejected")
    photo = max(message["photo"], key=lambda photo: photo["width"] * photo["height"])
    product = Product.objects.select_for_update().get(pk=post.product_id) if post.product_id else None
    created = product is None
    if created:
        product = Product(
            category=_category(), catalog_scope=Product.CatalogScope.SAME_DAY,
            # Explicit temporary unique slug also prevents concurrent empty-slug inserts.
            slug=f"telegram-{abs(post.telegram_chat_id)}-{post.telegram_message_id}",
        )
    elif product.catalog_scope != Product.CatalogScope.SAME_DAY:
        raise SyncConfigurationError("linked_product_scope_changed")
    new_image = None
    if not product.cover_image or post.telegram_file_id != photo["file_id"]:
        try:
            new_image = normalize_admin_image(download_photo(photo["file_id"]))
        except ImageUploadError:
            return _record_failure(post, "invalid_image", "product media rejected")
    product.pricing_type = Product.PricingType.FIXED
    product.price = price
    product.publish_status = Product.PublishStatus.PUBLISHED
    # Caption edits must never restore stock or override an admin's SOLD state.
    if post.sold_at:
        product.status = Product.Status.SOLD
    if post.withdrawn_at:
        product.status = Product.Status.WITHDRAWN
    if product.status in {Product.Status.SOLD, Product.Status.WITHDRAWN}:
        product.stock_status = Product.StockStatus.OUT_OF_STOCK
    if new_image is not None:
        product.cover_image = new_image
    try:
        product.save()
    finally:
        if new_image is not None and product.cover_image and product.cover_image._committed:
            stored_files.append((product.cover_image.storage, product.cover_image.name))
    post.product = product
    post.telegram_file_id = photo["file_id"]
    post.last_error = ""
    post.studio_error = studio_error
    post.save()
    if metadata:
        sync_daily(post, message, metadata=metadata)
    event = "Telegram product created" if created else "product updated"
    logger.info("%s product_id=%s chat_id=%s message_id=%s", event, product.pk,
                post.telegram_chat_id, post.telegram_message_id)
    return "created" if created else "updated"


def _automatic_origin(message, group_id, channel_id):
    origin = message.get("forward_origin", {})
    if (str(message["chat"]["id"]) == group_id
            and message.get("is_automatic_forward") is True
            and origin.get("type") == "channel"
            and str(origin["chat"]["id"]) == channel_id):
        return _post(origin["chat"]["id"], origin["message_id"])
    return None


def _link(message, post):
    link, _ = TelegramDiscussionMessage.objects.get_or_create(
        telegram_chat_id=message["chat"]["id"],
        telegram_message_id=message["message_id"], defaults={"post": post},
    )
    if link.post_id != post.pk:
        raise InvalidSource("conflicting_message_identity")


def _find_group_post(message, group_id, channel_id):
    post = _automatic_origin(message, group_id, channel_id)
    if post:
        _link(message, post)
        return post
    reply = message.get("reply_to_message")
    if reply and str(reply["chat"]["id"]) != group_id:
        return None
    if reply:
        post = _automatic_origin(reply, group_id, channel_id)
        if post:
            _link(reply, post)
        else:
            link = TelegramDiscussionMessage.objects.filter(
                telegram_chat_id=message["chat"]["id"],
                telegram_message_id=reply["message_id"],
            ).first()
            post = TelegramSameDayPost.objects.select_for_update().get(pk=link.post_id) if link else None
    # Telegram can supply the root identity for a nested comment, even if its
    # parent update was not seen. Only an already verified mapping is accepted.
    if post is None and message.get("message_thread_id"):
        link = TelegramDiscussionMessage.objects.filter(
            telegram_chat_id=message["chat"]["id"],
            telegram_message_id=message["message_thread_id"],
        ).first()
        post = TelegramSameDayPost.objects.select_for_update().get(pk=link.post_id) if link else None
    if post:
        if str(post.telegram_chat_id) != channel_id:
            raise InvalidSource("old_channel_mapping")
        _link(message, post)
    return post


def _is_sold(message):
    text = message.get("text", "").translate(str.maketrans("يك", "یک")).replace("\u200c", " ")
    return " ".join(text.split()).strip(".!، ") == "فروخته شد"


def _is_withdrawn(message):
    text = message.get("text", "").translate(str.maketrans("يك", "یک")).replace("\u200c", " ")
    return " ".join(text.split()).strip(".!، ") == "کشیده شد"


def _can_sell(message, *, channel=False):
    # Forwarded copies are never commands, even from a permitted operator.
    if message.get("forward_origin") or message.get("is_automatic_forward"):
        return False
    if channel:
        return True  # Telegram only lets channel publishers publish channel posts.
    # Require an identifiable, explicitly permitted human, not anonymous admins
    # or comments posted as another channel (including this channel).
    sender = message.get("from", {})
    return (not message.get("sender_chat") and not sender.get("is_bot", False)
            and TelegramBotUser.objects.filter(
                telegram_user_id=sender.get("id"), is_active=True,
                can_manage_same_day=True,
            ).exists())


def _sell(post, *, withdrawn=False):
    from ..studio_ingestion import sync_daily_status
    if withdrawn:
        if post.withdrawn_at:
            return "duplicate_ignored"
        post.withdrawn_at = timezone.now()
        post.save(update_fields=["withdrawn_at", "updated_at"])
        if post.product_id:
            Product.objects.filter(pk=post.product_id).update(
                status=Product.Status.WITHDRAWN, stock_status=Product.StockStatus.OUT_OF_STOCK,
                updated_at=timezone.now(),
            )
        sync_daily_status(post)
        logger.info("product marked WITHDRAWN chat_id=%s message_id=%s", post.telegram_chat_id, post.telegram_message_id)
        return "withdrawn"
    if post.withdrawn_at:
        return "terminal_status_ignored"
    if post.sold_at:
        logger.info("duplicate ignored sold chat_id=%s message_id=%s", post.telegram_chat_id, post.telegram_message_id)
        return "duplicate_ignored"
    post.sold_at = timezone.now()
    post.save(update_fields=["sold_at", "updated_at"])
    if post.product_id:
        Product.objects.filter(pk=post.product_id).update(
            status=Product.Status.SOLD, stock_status=Product.StockStatus.OUT_OF_STOCK,
            updated_at=timezone.now(),
        )
    sync_daily_status(post)
    logger.info("product marked SOLD product_id=%s chat_id=%s message_id=%s",
                post.product_id, post.telegram_chat_id, post.telegram_message_id)
    return "sold"


def process_update(kind, message, update_id):
    channel_id = str(settings.TELEGRAM_CHANNEL_ID)
    group_id = str(settings.TELEGRAM_DISCUSSION_GROUP_ID)
    direct_id = str(settings.TELEGRAM_SAME_DAY_GROUP_ID)
    custom_id = str(settings.TELEGRAM_STUDIO_CUSTOM_GROUP_ID)
    custom = (kind in {"message", "edited_message"}
              and message["chat"]["type"] in {"group", "supergroup"}
              and custom_id and str(message["chat"]["id"]) == custom_id)
    if custom:
        if custom_id in {channel_id, group_id, direct_id}:
            raise SyncConfigurationError("overlapping_source_ids")
        from ..studio_ingestion import process_custom
        stored_files = []
        try:
            with transaction.atomic():
                return process_custom(message, update_id, stored_files)
        except Exception:
            for storage, name in stored_files:
                try:
                    if not StudioProduct.objects.filter(image=name).exists():
                        storage.delete(name)
                except Exception:
                    logger.error("studio image cleanup failed; manual review required")
            raise
    if not (channel_id or direct_id) or not settings.TELEGRAM_SAME_DAY_CATEGORY_ID:
        raise SyncConfigurationError("same_day_not_configured")
    channel = (kind in {"channel_post", "edited_channel_post"}
               and message["chat"]["type"] == "channel"
               and str(message["chat"]["id"]) == channel_id)
    group = (kind in {"message", "edited_message"}
             and message["chat"]["type"] in {"group", "supergroup"}
             and group_id and str(message["chat"]["id"]) == group_id)
    direct = (kind in {"message", "edited_message"}
              and message["chat"]["type"] in {"group", "supergroup"}
              and direct_id and str(message["chat"]["id"]) == direct_id)
    if direct and direct_id in {channel_id, group_id}:
        raise SyncConfigurationError("overlapping_source_ids")
    if not channel and not group and not direct:
        raise InvalidSource("unauthorized_chat")
    stored_files = []
    try:
        with transaction.atomic():
            if direct:
                from .group import sync_group
                return sync_group(message, update_id, stored_files)
            if channel and (message.get("photo") or (kind == "edited_channel_post" and TelegramSameDayPost.objects.filter(
                telegram_chat_id=message["chat"]["id"], telegram_message_id=message["message_id"],
            ).exists())):
                return _sync_product(message, update_id, stored_files)
            if group:
                post = _find_group_post(message, group_id, channel_id)
            else:
                reply = message.get("reply_to_message")
                post = None
                if reply and reply["chat"]["id"] == message["chat"]["id"]:
                    post = TelegramSameDayPost.objects.select_for_update().filter(
                        telegram_chat_id=message["chat"]["id"],
                        telegram_message_id=reply["message_id"],
                    ).first()
                    if post is None and reply.get("photo") and (_is_sold(message) or _is_withdrawn(message)) and _can_sell(message, channel=True):
                        post = _post(message["chat"]["id"], reply["message_id"])
            if not (_is_sold(message) or _is_withdrawn(message)):
                return "ignored"
            if not _can_sell(message, channel=channel):
                raise InvalidSource("unauthorized_sold_actor")
            if post is None:
                logger.info("unknown reply ignored chat_id=%s message_id=%s",
                            message["chat"]["id"], message["message_id"])
                return "unknown_reply_ignored"
            return _sell(post, withdrawn=_is_withdrawn(message))
    except Exception:
        # Storage isn't transactional. Remove only newly written, unreferenced
        # files after a rollback; never delete an old/admin-uploaded image.
        for storage, name in stored_files:
            try:
                if not Product.objects.filter(cover_image=name).exists():
                    storage.delete(name)
            except Exception:
                logger.error("new image cleanup failed; manual review required")
        raise
