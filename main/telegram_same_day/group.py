"""Direct group products: photo identity persists while waiting for a price reply."""
import logging

from ..models import TelegramDiscussionMessage, TelegramSameDayPost
from .price import PriceError, parse_group_price
from .service import InvalidSource, _can_sell, _is_sold, _is_withdrawn, _link, _post, _sell, _sync_product

logger = logging.getLogger("main.telegram_same_day")


def sync_group(message, update_id, stored_files):
    if not (message.get("photo") or message.get("reply_to_message")):
        return "ignored"
    if not _can_sell(message):
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
    # A reply may arrive before the original webhook. Trust only a permitted
    # original photographer, never a forwarded image or an unrelated member.
    if post is None and reply.get("photo") and _can_sell(reply):
        post = _post(chat_id, reply["message_id"])
        post.source_photo = {key: reply[key] for key in
                             ("message_id", "chat", "date", "photo", "media_group_id") if key in reply}
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
    source["caption"] = text
    source["edit_date"] = message.get("edit_date", message.get("date", 0))
    return _sync_product(source, update_id, stored_files, direct_group=True)
