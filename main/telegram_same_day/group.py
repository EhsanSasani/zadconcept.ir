"""Direct group products: photo identity persists while waiting for a price reply."""
import logging

from django.conf import settings

from ..models import Product, StudioDelivery, StudioProduct, TelegramDiscussionMessage, TelegramSameDayPost
from .price import PriceError, parse_group_price, parse_price_command
from .service import InvalidSource, SyncConfigurationError, _is_sold, _is_withdrawn, _link, _lock_post, _post, _sell, _sync_product

logger = logging.getLogger("main.telegram_same_day")


def _record_for(post):
    if post.product_id:
        return StudioProduct.objects.select_for_update().filter(product_id=post.product_id).first()
    return StudioProduct.objects.select_for_update().filter(
        telegram_chat_id=post.telegram_chat_id, telegram_message_id=post.telegram_message_id,
    ).first()


def _status_feedback(record, result):
    action = "فروش ثبت شد" if result == "sold" else "خروج از فروش ثبت شد"
    status = "فروخته‌شده" if result == "sold" else "جمع‌آوری‌شده"
    factor = f"\nفاکتور: {record.factor_code}" if record else ""
    return f"{action}{factor}\nوضعیت: {status}"


def _group_member(message):
    """Authenticated updates from the configured group need no user allowlist."""
    chat = message.get("chat", {})
    if (chat.get("type") not in {"group", "supergroup"}
            or str(chat.get("id")) != str(settings.TELEGRAM_SAME_DAY_GROUP_ID)):
        return False
    sender_chat = message.get("sender_chat")
    if sender_chat:
        return sender_chat.get("id") == chat.get("id")
    sender = message.get("from", {})
    return bool(sender.get("id")) and not sender.get("is_bot", False)


def sync_group(message, update_id, stored_files):
    if not (message.get("photo") or message.get("reply_to_message")):
        return "ignored"
    if (message.get("from", {}).get("is_bot") and StudioProduct.objects.filter(
            source=StudioProduct.Source.PORTAL, telegram_chat_id=message["chat"]["id"],
            telegram_message_id=message["message_id"]).exists()):
        return "portal_echo_ignored"
    if not _group_member(message):
        raise InvalidSource("unauthorized_group_operator")
    if message.get("photo"):
        result = _sync_product(message, update_id, stored_files, direct_group=True)
        _link(message, _post(message["chat"]["id"], message["message_id"]))
        return result
    reply = message["reply_to_message"]
    chat_id = message["chat"]["id"]
    if reply["chat"]["id"] != chat_id:
        raise InvalidSource("foreign_reply")
    post = TelegramSameDayPost.objects.filter(
        telegram_chat_id=chat_id, telegram_message_id=reply["message_id"],
    ).first()
    if post is not None:
        post = _lock_post(post)
    if post is None:
        link = TelegramDiscussionMessage.objects.filter(
            telegram_chat_id=chat_id, telegram_message_id=reply["message_id"],
            post__telegram_chat_id=chat_id,
        ).first()
        if link:
            post = _post(chat_id, link.post.telegram_message_id)
    if post is None and reply.get("photo") and reply.get("from", {}).get("is_bot"):
        # A human can reply immediately while the sending worker is committing
        # the returned message identity. Do not acknowledge-and-lose that sale.
        # Matching text is used ONLY to defer, never to trust a bot's identity.
        from ..studio_delivery import product_caption
        pending = StudioDelivery.objects.filter(
            chat_id=chat_id, action=StudioDelivery.Action.PUBLISH,
            status__in=[StudioDelivery.Status.SENDING, StudioDelivery.Status.UNCERTAIN],
        ).select_related("record")
        if any(reply.get("caption", "") == product_caption(job.record) for job in pending):
            raise SyncConfigurationError("portal_message_identity_pending")
        # The worker can commit between our first identity lookup and the
        # pending-job query. Re-read before acknowledging an unknown reply.
        mapped = TelegramSameDayPost.objects.filter(
            telegram_chat_id=chat_id, telegram_message_id=reply["message_id"],
        ).first()
        if mapped is not None:
            post = _lock_post(mapped)
    # A reply may arrive before the original webhook. The original photo must
    # also belong to this configured group; all its members are permitted.
    if post is None and reply.get("photo") and _group_member(reply):
        post = _post(chat_id, reply["message_id"])
        post.source_photo = {key: reply[key] for key in
                             ("message_id", "chat", "date", "photo", "media_group_id", "caption") if key in reply}
        post.save()
    if post is None:
        logger.info("unknown reply ignored chat_id=%s message_id=%s", chat_id, message["message_id"])
        return "unknown_reply_ignored"
    _link(message, post)
    record = _record_for(post)
    if _is_sold(message) or _is_withdrawn(message):
        result = _sell(post, withdrawn=_is_withdrawn(message))
        if result in {"sold", "withdrawn"}:
            return {"result": result, "feedback": _status_feedback(record, result),
                    "reply_to_message_id": message["message_id"]}
        return result
    try:
        price = parse_price_command(message.get("text", ""))
    except PriceError as error:
        if error.args and error.args[0] != "not_price_command":
            return {"result": "rejected", "feedback": "قیمت معتبر نیست. نمونه: قیمت: 2500000",
                    "reply_to_message_id": message["message_id"]}
        price = None
    if price is not None and post.product_id:
        Product.objects.filter(pk=post.product_id).update(price=price)
        if record:
            record.price = price
            record.save(update_fields=["price", "updated_at"])
        factor = f"\nفاکتور: {record.factor_code}" if record else ""
        return {"result": "price_updated",
                "feedback": f"قیمت به‌روزرسانی شد{factor}\nقیمت جدید: {price:,.0f} تومان",
                "reply_to_message_id": message["message_id"]}
    if record and record.source in {
        StudioProduct.Source.PORTAL, StudioProduct.Source.DASHBOARD, StudioProduct.Source.ADMIN,
    }:
        return "portal_reply_ignored"
    text = message.get("text", "")
    try:
        parse_group_price(text)
    except PriceError:
        # Ordinary conversation is not a price edit. Numeric/price-like replies
        # fail closed, hiding a previous price rather than retaining a stale one.
        if not any(char.isdigit() for char in text) and not any(word in text for word in ("قیمت", "مبلغ", "بها", "تومان", "تومن", "میلیون", "هزار")):
            return "ignored"
    if not post.source_photo:
        return "missing_photo_ignored"
    source = dict(post.source_photo)
    try:
        price = parse_group_price(text)
    except PriceError:
        source["caption"] = text
    else:
        metadata_lines = [line for line in post.source_photo.get("caption", "").splitlines()
                          if line.strip().lower().startswith(("florist:", "type:", "factor:",
                                                               "فلوریست:", "نوع:", "فاکتور:"))]
        source["caption"] = "\n".join([*metadata_lines, f"قیمت: {price}"])
    source["edit_date"] = message.get("edit_date", message.get("date", 0))
    return _sync_product(source, update_id, stored_files, direct_group=True)
