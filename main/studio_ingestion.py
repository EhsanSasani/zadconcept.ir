"""Validated production ledger inputs from Telegram. Public catalog stays separate."""
import re
from datetime import datetime, timezone as dt_timezone

from django.core.exceptions import ValidationError
from django.utils import timezone

from .image_pipeline import ImageUploadError, normalize_admin_image
from .models import Florist, StudioIngestionIssue, StudioProduct
from .telegram_same_day.client import download_photo
from .telegram_same_day.price import DIGITS, PriceError, parse_price_command


class StudioInputError(ValueError):
    pass


TYPE_ALIASES = {
    "box": "box", "باکس": "box", "باکس گل": "box",
    "bouquet": "bouquet", "دسته گل": "bouquet", "بوکت": "bouquet",
    "jar": "jar", "جار": "jar", "جار گل": "jar",
    "stand": "stand", "استند": "stand", "استند گل": "stand",
    "basket": "basket", "سبد": "basket", "سبد گل": "basket",
    "bridal": "bridal", "دسته گل عروس": "bridal",
    "car": "car", "ماشین عروس": "car",
    "other": "other", "سایر": "other",
}
FIELDS = {"florist": "florist", "فلوریست": "florist", "type": "type", "نوع": "type",
          "factor": "factor", "فاکتور": "factor", "price": "price", "قیمت": "price"}
REQUIRED = {"florist", "type", "factor", "price"}


def parse_caption(caption):
    if not isinstance(caption, str) or len(caption) > 1024:
        raise StudioInputError("کپشن معتبر نیست؛ چهار فیلد florist، type، factor و price لازم است.")
    fields = {}
    for raw in caption.translate(DIGITS).replace("\u200c", " ").splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.fullmatch(r"([^:=：]+)\s*[:=：]\s*(.+)", line)
        if not match or match[1].strip().casefold() not in FIELDS:
            raise StudioInputError("هر خط باید یکی از فیلدهای florist، type، factor و price باشد.")
        key = FIELDS[match[1].strip().casefold()]
        if key in fields:
            raise StudioInputError(f"فیلد {key} تکراری است.")
        fields[key] = match[2].strip()
    missing = REQUIRED - fields.keys()
    if missing:
        raise StudioInputError("فیلدهای ناقص: " + ", ".join(sorted(missing)))
    code = fields["florist"].lower()
    if not re.fullmatch(r"[a-z0-9_-]{1,24}", code):
        raise StudioInputError("کد فلوریست نامعتبر است.")
    product_type = TYPE_ALIASES.get(fields["type"].casefold())
    if not product_type:
        raise StudioInputError("نوع محصول تعریف نشده است.")
    factor = fields["factor"].upper()
    if not re.fullmatch(r"[A-Z0-9-]{1,40}", factor):
        raise StudioInputError("شماره فاکتور نامعتبر است.")
    price_text = fields["price"].replace(",", "").replace("٬", "")
    if not re.fullmatch(r"[0-9]{1,12}", price_text) or not 0 < int(price_text) <= 999_999_999_999:
        raise StudioInputError("قیمت را به تومان و فقط با عدد مثبت وارد کنید.")
    return dict(florist_code=code, product_type=product_type, factor_code=factor,
                price=int(price_text))


def resolve_metadata(caption, *, identity=None):
    values = parse_caption(caption)
    code = values.pop("florist_code")
    existing = None
    if identity:
        existing = StudioProduct.objects.filter(telegram_chat_id=identity[0], telegram_message_id=identity[1]).first()
    florist = Florist.objects.filter(code=code).first()
    if not florist or (not florist.is_active and (not existing or existing.florist_id != florist.pk)):
        raise StudioInputError("کد فلوریست تعریف نشده یا غیرفعال است.")
    if existing and existing.factor_code != values["factor_code"]:
        raise StudioInputError("شماره فاکتور پس از ثبت اولیه قابل تغییر نیست.")
    values["florist"] = florist
    duplicate = StudioProduct.objects.filter(factor_code=values["factor_code"])
    if identity:
        duplicate = duplicate.exclude(telegram_chat_id=identity[0], telegram_message_id=identity[1])
    if duplicate.exists():
        raise StudioInputError("شماره فاکتور قبلاً ثبت شده است.")
    return values


def _event_time(message):
    return datetime.fromtimestamp(message["date"], tz=dt_timezone.utc)


def sync_daily(post, message, *, metadata=None):
    """Called inside the existing row-locked Same-Day transaction."""
    if not post.product_id:
        return
    identity = post.telegram_chat_id, post.telegram_message_id
    if metadata is None:
        metadata = resolve_metadata(message.get("caption", ""), identity=identity)
    record = StudioProduct.objects.select_for_update().filter(
        telegram_chat_id=identity[0], telegram_message_id=identity[1],
    ).first()
    if record and record.status == StudioProduct.Status.DELETED:
        return
    if record and record.factor_code != metadata["factor_code"]:
        raise StudioInputError("شماره فاکتور پس از ثبت اولیه قابل تغییر نیست.")
    if record is None:
        record = StudioProduct(telegram_chat_id=identity[0], telegram_message_id=identity[1],
                               produced_at=post.telegram_created_at or timezone.now(),
                               source=StudioProduct.Source.TELEGRAM_DAILY,
                               production_type=StudioProduct.ProductionType.DAILY)
    record.product = post.product
    # Retain the media path even if an admin later removes the public Product.
    record.image = post.product.cover_image.name
    record.florist = metadata["florist"]
    record.factor_code = metadata["factor_code"]
    record.product_type = metadata["product_type"]
    record.price = metadata["price"]
    record.telegram_file_id = post.telegram_file_id
    if message.get("from", {}).get("id"):
        record.telegram_sender_id = message["from"]["id"]
    record.revision_date = post.revision_date
    record.revision_update_id = post.revision_update_id
    if post.withdrawn_at:
        record.status, record.withdrawn_at = StudioProduct.Status.WITHDRAWN, post.withdrawn_at
    elif post.sold_at:
        record.status, record.sold_at = StudioProduct.Status.SOLD, post.sold_at
    record.full_clean()
    record.save()


def sync_daily_status(post):
    record = StudioProduct.objects.select_for_update().filter(
        telegram_chat_id=post.telegram_chat_id, telegram_message_id=post.telegram_message_id,
    ).first()
    if not record or record.status == StudioProduct.Status.DELETED:
        return
    if post.withdrawn_at:
        record.status, record.withdrawn_at = StudioProduct.Status.WITHDRAWN, post.withdrawn_at
    elif post.sold_at and record.status != StudioProduct.Status.WITHDRAWN:
        record.status, record.sold_at = StudioProduct.Status.SOLD, post.sold_at
    record.save(update_fields=["status", "sold_at", "withdrawn_at", "updated_at"])
    from .studio_delivery import queue_retirement
    queue_retirement(record)


def _trusted_custom_member(message):
    sender = message.get("from", {})
    chat = message.get("chat", {})
    return (not sender.get("is_bot") and bool(sender.get("id")) and
            not message.get("sender_chat") and not message.get("forward_origin") and
            chat.get("type") in {"group", "supergroup"})


def _reject_custom(chat_id, message_id, reason):
    StudioIngestionIssue.objects.update_or_create(
        telegram_chat_id=chat_id, telegram_message_id=message_id,
        defaults={"reason": reason, "resolved_at": None, "resolved_by": None},
    )
    return {"result": "rejected", "feedback": reason, "reply_to_message_id": message_id}


def _status_feedback(record, *, sold):
    action = "فروش ثبت شد" if sold else "خروج از فروش ثبت شد"
    status = "فروخته‌شده" if sold else "جمع‌آوری‌شده"
    return f"{action}\nفاکتور: {record.factor_code}\nوضعیت: {status}"


def process_custom(message, update_id, stored_files):
    from .telegram_same_day.service import InvalidSource, _is_sold, _is_withdrawn
    if not _trusted_custom_member(message):
        raise InvalidSource("unauthorized_custom_actor")
    chat_id, message_id = message["chat"]["id"], message["message_id"]
    reply = message.get("reply_to_message")
    if not reply and not message.get("photo"):
        return {"result": "ignored"}
    if reply and not message.get("photo"):
        if reply["chat"]["id"] != chat_id:
            raise InvalidSource("foreign_custom_reply")
        sold, withdrawn = _is_sold(message), _is_withdrawn(message)
        price = None
        if not (sold or withdrawn):
            try:
                price = parse_price_command(message.get("text", ""))
            except PriceError as error:
                if error.args and error.args[0] != "not_price_command":
                    return {"result": "rejected", "feedback": "قیمت معتبر نیست. نمونه: قیمت: 2500000",
                            "reply_to_message_id": message_id}
                return {"result": "ignored"}
        record = StudioProduct.objects.select_for_update().filter(
            telegram_chat_id=chat_id, telegram_message_id=reply["message_id"],
            production_type=StudioProduct.ProductionType.CUSTOM,
            source__in=[StudioProduct.Source.TELEGRAM_CUSTOM, StudioProduct.Source.PORTAL],
        ).first()
        if not record and reply.get("photo") and reply.get("from", {}).get("is_bot"):
            # A sale can arrive before the publishing worker commits its message
            # identity. Like the ready-group path, defer instead of losing it.
            from .models import StudioDelivery
            from .studio_delivery import pending_caption_matches
            from .telegram_same_day.service import SyncConfigurationError
            pending = StudioDelivery.objects.filter(
                chat_id=chat_id, action=StudioDelivery.Action.PUBLISH,
                record__production_type=StudioProduct.ProductionType.CUSTOM,
                status__in=[StudioDelivery.Status.SENDING, StudioDelivery.Status.UNCERTAIN],
            ).select_related("record")
            if any(pending_caption_matches(job.record, reply.get("caption", "")) for job in pending):
                raise SyncConfigurationError("portal_message_identity_pending")
            # The worker may commit between the first lookup and pending query.
            record = StudioProduct.objects.select_for_update().filter(
                telegram_chat_id=chat_id, telegram_message_id=reply["message_id"],
                production_type=StudioProduct.ProductionType.CUSTOM,
                source__in=[StudioProduct.Source.TELEGRAM_CUSTOM, StudioProduct.Source.PORTAL],
            ).first()
        if not record:
            return {"result": "unknown_reply_ignored"}
        if record.status == StudioProduct.Status.DELETED:
            return {"result": "admin_deleted_ignored"}
        if price is not None:
            revision = message.get("edit_date", message.get("date", 0))
            if not revision or (revision, update_id) <= (record.revision_date, record.revision_update_id):
                return {"result": "duplicate_ignored"}
            record.price = price
            record.revision_date, record.revision_update_id = revision, update_id
            record.save(update_fields=["price", "revision_date", "revision_update_id", "updated_at"])
            return {"result": "price_updated",
                    "feedback": f"قیمت به‌روزرسانی شد\nفاکتور: {record.factor_code}\nقیمت جدید: {record.price:,.0f} تومان",
                    "reply_to_message_id": message_id}
        if record.status != StudioProduct.Status.AVAILABLE:
            return {"result": "duplicate_ignored"}
        if sold:
            record.status, record.sold_at = StudioProduct.Status.SOLD, timezone.now()
        else:
            record.status, record.withdrawn_at = StudioProduct.Status.WITHDRAWN, timezone.now()
        record.save(update_fields=["status", "sold_at", "withdrawn_at", "updated_at"])
        from .studio_delivery import queue_retirement
        queue_retirement(record)
        return {"result": "status_updated", "feedback": _status_feedback(record, sold=sold),
                "reply_to_message_id": message_id}
    if not message.get("photo") or message.get("media_group_id"):
        return _reject_custom(chat_id, message_id, "یک عکس تکی همراه کپشن کامل ارسال کنید.")
    identity = chat_id, message_id
    # A portal message has a deliberately minimal caption; never re-import it.
    if StudioProduct.objects.filter(telegram_chat_id=chat_id, telegram_message_id=message_id,
                                    source=StudioProduct.Source.PORTAL).exists():
        return {"result": "portal_message_ignored"}
    try:
        metadata = resolve_metadata(message.get("caption", ""), identity=identity)
    except StudioInputError as error:
        return _reject_custom(chat_id, message_id, str(error))
    revision = message.get("edit_date", message.get("date", 0))
    record = StudioProduct.objects.select_for_update().filter(
        telegram_chat_id=chat_id, telegram_message_id=message_id,
    ).first()
    if record and record.status == StudioProduct.Status.DELETED:
        return {"result": "admin_deleted_ignored"}
    if record and (revision, update_id) <= (record.revision_date, record.revision_update_id):
        return {"result": "duplicate_ignored"}
    if record and record.factor_code != metadata["factor_code"]:
        return _reject_custom(chat_id, message_id, "شماره فاکتور پس از ثبت تغییر نمی‌کند.")
    photo = max(message["photo"], key=lambda item: item["width"] * item["height"])
    new_image = None
    if not record or record.telegram_file_id != photo["file_id"]:
        try:
            new_image = normalize_admin_image(download_photo(photo["file_id"]))
        except ImageUploadError:
            return _reject_custom(chat_id, message_id, "تصویر معتبر نیست؛ یک عکس تکی تازه ارسال کنید.")
    created = record is None
    if created:
        record = StudioProduct(telegram_chat_id=chat_id, telegram_message_id=message_id,
                               production_type=StudioProduct.ProductionType.CUSTOM,
                               source=StudioProduct.Source.TELEGRAM_CUSTOM,
                               produced_at=_event_time(message))
    record.factor_code = metadata["factor_code"]
    record.florist = metadata["florist"]
    record.product_type = metadata["product_type"]
    record.price = metadata["price"]
    record.telegram_file_id = photo["file_id"]
    record.telegram_sender_id = message["from"]["id"]
    record.revision_date, record.revision_update_id = revision, update_id
    if new_image is not None:
        record.image = new_image
    record.full_clean()
    try:
        record.save()
    finally:
        if new_image is not None and record.image and record.image._committed:
            stored_files.append((record.image.storage, record.image.name))
    StudioIngestionIssue.objects.filter(telegram_chat_id=chat_id, telegram_message_id=message_id,
                                        resolved_at__isnull=True).update(resolved_at=timezone.now())
    return {"result": "created" if created else "updated",
            "feedback": f"ثبت شد · فاکتور {record.factor_code} · {record.florist.name} · {record.get_product_type_display()} · {record.price:,.0f} تومان",
            "reply_to_message_id": message_id}
