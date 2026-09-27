"""Direct group products: photo identity persists while waiting for a price reply."""
import logging

from django.conf import settings

from ..models import TelegramDiscussionMessage, TelegramSameDayPost
from .price import PriceError, parse_group_price
from .service import InvalidSource, _is_sold, _is_withdrawn, _link, _post, _sell, _sync_product

logger = logging.getLogger("main.telegram_same_day")


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
    post = TelegramSameDayPost.objects.select_for_update().filter(
        telegram_chat_id=chat_id, telegram_message_id=reply["message_id"],
    ).first()
    if post is None:
        link = TelegramDiscussionMessage.objects.filter(
            telegram_chat_id=chat_id, telegram_message_id=reply["message_id"],
            post__telegram_chat_id=chat_id,
        ).first()
        if link:
            post = _post(chat_id, link.post.telegram_message_id)
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
    if _is_sold(message) or _is_withdrawn(message):
        return _sell(post, withdrawn=_is_withdrawn(message))
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
