"""Telegram outbox with short database leases and explicit ambiguous-send recovery."""
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone as datetime_timezone
from io import BytesIO

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from PIL import Image

from .models import Product, StudioDelivery, StudioProduct, TelegramSameDayPost
from . import studio_transport

logger = logging.getLogger(__name__)
READY = (StudioDelivery.Status.PENDING, StudioDelivery.Status.RETRY)


def _lock_record(record_id):
    # Product saves (including Django Admin) acquire the public row before the
    # ledger signal runs. Match that order in portal transitions and completion.
    product_id = StudioProduct.objects.values_list("product_id", flat=True).get(pk=record_id)
    if product_id:
        Product.objects.select_for_update().filter(pk=product_id).first()
    return StudioProduct.objects.select_for_update().get(pk=record_id)


def product_caption(record):
    return f"قیمت: {record.price:,.0f} تومان\nفاکتور: {record.factor_code}"


def pending_caption_matches(record, caption):
    """Only defer an in-flight reply; a caption never establishes message ownership.

    The invoice is immutable, while a manager can correct the price during send.
    Accept only our narrow outbound shape, so that correction cannot lose a sale.
    """
    if not isinstance(caption, str) or len(caption) > 1024:
        return False
    return bool(re.fullmatch(
        rf"قیمت: [0-9,]+ تومان\nفاکتور: {re.escape(record.factor_code)}", caption,
    ))


def delivery_summary(record):
    group_label = "گروه سفارشی‌ها" if record.production_type == StudioProduct.ProductionType.CUSTOM else "گروه آماده‌ها"
    jobs = list(record.deliveries.all())
    job = next((item for item in jobs if item.action == StudioDelivery.Action.RETIRE), None)
    job = job or next((item for item in jobs if item.action == StudioDelivery.Action.PUBLISH), None)
    if not job:
        return {"state": "internal", "label": "ثبت استودیو", "detail": "ارسالی از پنل برای این محصول وجود ندارد."}
    if job.status == StudioDelivery.Status.UNCERTAIN:
        return {"state": "uncertain", "label": "در حال بررسی ارسال", "detail": "نتیجهٔ ارسال مشخص نیست. مدیر پیام گروه را بررسی می‌کند؛ محصول را دوباره ثبت نکنید."}
    if job.status == StudioDelivery.Status.FAILED:
        return {"state": "failed", "label": "تلگرام نیازمند رسیدگی", "detail": "محصول ذخیره شده است؛ مدیر مشکل ارسال تلگرام را بررسی می‌کند."}
    if job.status != StudioDelivery.Status.SENT:
        label = "در صف خروج از گروه" if job.action == StudioDelivery.Action.RETIRE else f"در صف ارسال به {group_label}"
        return {"state": "pending", "label": label, "detail": "ثبت محصول کامل است؛ ارسال به‌صورت خودکار پیگیری می‌شود."}
    if job.outcome == "caption_marked":
        return {"state": "sent", "label": "وضعیت در گروه درج شد", "detail": "حذف پیام ممکن نبود؛ کپشن پیام با وضعیت خروج به‌روز شد."}
    if job.action == StudioDelivery.Action.RETIRE:
        return {"state": "sent", "label": f"از {group_label} خارج شد", "detail": "سابقهٔ محصول در پنل محفوظ است."}
    if job.outcome == "not_available":
        return {"state": "sent", "label": "ارسال لازم نبود", "detail": "پیش از ارسال به تلگرام، محصول از موجودی خارج شد."}
    return {"state": "sent", "label": f"به {group_label} ارسال شد", "detail": "عکس، قیمت و شمارهٔ فاکتور در گروه ثبت شده است."}


def queue_retirement(record):
    """Call in the status transaction. Only messages emitted by our outbox retire."""
    if (record.status == StudioProduct.Status.AVAILABLE
            or not record.telegram_chat_id or not record.telegram_message_id):
        return None
    published = record.deliveries.filter(action=StudioDelivery.Action.PUBLISH).first()
    if not published:
        return None
    job, created = StudioDelivery.objects.get_or_create(
        record=record, action=StudioDelivery.Action.RETIRE,
        defaults={"chat_id": record.telegram_chat_id, "message_id": record.telegram_message_id,
                  "telegram_created_at": published.telegram_created_at if published else None},
    )
    # An older caption fallback may need to reflect a later terminal update. A
    # deleted message is already absent and must not be posted again.
    if not created and job.status == StudioDelivery.Status.SENT and job.outcome == "caption_marked":
        job.status, job.next_attempt_at, job.last_error = StudioDelivery.Status.RETRY, timezone.now(), ""
        job.save(update_fields=["status", "next_attempt_at", "last_error", "updated_at"])
    return job


def set_portal_status(record, status, *, actor):
    if not getattr(actor, "is_active", False) or not actor.has_perm("main.change_studioproduct"):
        raise PermissionDenied
    allowed = {StudioProduct.Status.SOLD, StudioProduct.Status.WITHDRAWN, StudioProduct.Status.CANCELLED}
    if status not in allowed:
        raise ValidationError("وضعیت خروج معتبر نیست.")
    with transaction.atomic():
        record = _lock_record(record.pk)
        if not record.deliveries.filter(action=StudioDelivery.Action.PUBLISH).exists():
            raise ValidationError("برای این محصول پیام خروجی تلگرام ثبت نشده است.")
        if record.status == status:
            queue_retirement(record)
            return record
        if record.status != StudioProduct.Status.AVAILABLE:
            raise ValidationError("وضعیت نهایی این محصول قبلاً ثبت شده است.")
        now = timezone.now()
        record.status = status
        if status == StudioProduct.Status.SOLD:
            record.sold_at = now
        else:
            record.withdrawn_at = now
        record.save(update_fields=["status", "sold_at", "withdrawn_at", "updated_at"])
        if record.product_id:
            public_status = Product.Status.SOLD if status == StudioProduct.Status.SOLD else Product.Status.WITHDRAWN
            Product.objects.filter(pk=record.product_id).update(
                status=public_status, stock_status=Product.StockStatus.OUT_OF_STOCK, updated_at=now,
            )
            TelegramSameDayPost.objects.filter(product_id=record.product_id).update(
                **({"sold_at": now} if status == StudioProduct.Status.SOLD else {"withdrawn_at": now}),
                updated_at=now,
            )
        queue_retirement(record)
        return record


def soft_delete_product(record, *, actor, reason):
    """Soft-delete a ledger row while retiring any public/Telegram projection."""
    if not getattr(actor, "is_active", False) or not actor.has_perm("main.delete_studioproduct"):
        raise PermissionDenied
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("علت حذف را وارد کنید.")
    if len(reason) > 500:
        raise ValidationError("علت حذف نباید بیشتر از ۵۰۰ کاراکتر باشد.")

    with transaction.atomic():
        record = _lock_record(record.pk)
        if record.status == StudioProduct.Status.DELETED:
            return record

        now = timezone.now()
        record.status = StudioProduct.Status.DELETED
        record.deleted_at = now
        record.deleted_by = actor
        record.deletion_reason = reason
        record.save(update_fields=[
            "status", "deleted_at", "deleted_by", "deletion_reason", "updated_at",
        ])

        if record.product_id:
            Product.objects.filter(pk=record.product_id).update(
                status=Product.Status.WITHDRAWN,
                stock_status=Product.StockStatus.OUT_OF_STOCK,
                publish_status=Product.PublishStatus.DRAFT,
                updated_at=now,
            )
            TelegramSameDayPost.objects.filter(product_id=record.product_id).update(
                withdrawn_at=now, deleted_at=now, updated_at=now,
            )

        queue_retirement(record)
        return record


def retry_delivery(delivery_id):
    with transaction.atomic():
        job = StudioDelivery.objects.select_for_update().get(pk=delivery_id)
        if job.status not in {StudioDelivery.Status.FAILED, StudioDelivery.Status.RETRY}:
            raise ValidationError("این ارسال قابل تکرار نیست؛ ارسال نامشخص ابتدا باید در گروه بررسی شود.")
        if job.action == StudioDelivery.Action.PUBLISH and job.message_id:
            raise ValidationError("پیام این محصول قبلاً ثبت شده است.")
        job.status, job.next_attempt_at = StudioDelivery.Status.PENDING, timezone.now()
        job.locked_at = job.lock_token = None
        job.attempts, job.last_error = 0, ""
        job.save(update_fields=["status", "next_attempt_at", "locked_at", "lock_token", "attempts", "last_error", "updated_at"])
        return job


def retry_uncertain_delivery(delivery_id, *, actor, confirmed_absent):
    """Explicit audited human recovery after checking that no group message exists."""
    if not getattr(actor, "is_active", False) or not actor.has_perm("main.change_studioproduct"):
        raise PermissionDenied
    if confirmed_absent is not True:
        raise ValidationError("ابتدا نبودن پیام این فاکتور در گروه را تأیید کنید.")
    record_id = StudioDelivery.objects.values_list("record_id", flat=True).get(pk=delivery_id)
    with transaction.atomic():
        record = _lock_record(record_id)
        job = StudioDelivery.objects.select_for_update().get(pk=delivery_id)
        if (job.action != StudioDelivery.Action.PUBLISH or job.status != StudioDelivery.Status.UNCERTAIN
                or job.message_id or record.telegram_message_id):
            raise ValidationError("این ارسال نامشخص و بدون پیام ثبت‌شده نیست.")
        now = timezone.now()
        cutoff = now - timedelta(seconds=max(90, int(getattr(settings, "STUDIO_DELIVERY_LOCK_SECONDS", 120))))
        if job.locked_at and job.locked_at > cutoff:
            raise ValidationError("مهلت ارسال قبلی هنوز پایان نیافته است؛ کمی بعد گروه را دوباره بررسی کنید.")
        job.status, job.next_attempt_at = StudioDelivery.Status.PENDING, now
        job.locked_at = job.lock_token = None
        job.attempts, job.last_error = 0, ""
        job.manual_retry_by, job.manual_retry_at = actor, now
        job.save(update_fields=["status", "next_attempt_at", "locked_at", "lock_token", "attempts",
                                "last_error", "manual_retry_by", "manual_retry_at", "updated_at"])
        logger.warning("studio uncertain send manually requeued delivery_id=%s actor_id=%s", job.pk, actor.pk)
        return job


def _map_message(record, job, message_id, created_at, file_id=""):
    conflict = TelegramSameDayPost.objects.filter(telegram_chat_id=job.chat_id, telegram_message_id=message_id).first()
    if conflict and conflict.product_id not in {None, record.product_id}:
        raise ValidationError("این پیام به محصول دیگری متصل است.")
    if StudioProduct.objects.exclude(pk=record.pk).filter(
        telegram_chat_id=job.chat_id, telegram_message_id=message_id,
    ).exists():
        raise ValidationError("این پیام قبلاً برای محصول دیگری ثبت شده است.")
    other = TelegramSameDayPost.objects.filter(product_id=record.product_id).exclude(
        telegram_chat_id=job.chat_id, telegram_message_id=message_id,
    ).first() if record.product_id else None
    if other:
        raise ValidationError("این محصول قبلاً به پیام دیگری متصل است.")
    if record.production_type == StudioProduct.ProductionType.DAILY:
        post, _ = TelegramSameDayPost.objects.get_or_create(
            telegram_chat_id=job.chat_id, telegram_message_id=message_id,
        )
        post.product_id, post.telegram_created_at = record.product_id, created_at
        post.telegram_file_id, post.last_error = file_id, ""
        post.sold_at, post.withdrawn_at = record.sold_at, record.withdrawn_at
        # Portal metadata remains in the ledger; its two-line outbound caption must
        # never go through the legacy four-field ingestion parser.
        post.source_photo = {}
        post.save()
    record.telegram_chat_id, record.telegram_message_id = job.chat_id, message_id
    record.telegram_file_id = file_id
    record.save(update_fields=["telegram_chat_id", "telegram_message_id", "telegram_file_id", "updated_at"])
    job.message_id, job.telegram_created_at = message_id, created_at
    job.status, job.outcome, job.last_error = StudioDelivery.Status.SENT, "published", ""
    job.sent_at = timezone.now()
    job.locked_at = job.lock_token = None
    job.save()
    queue_retirement(record)


def reconcile_delivery(delivery_id, message_id, *, sent_at=None):
    """Trusted manager confirms an existing group message; this NEVER sends."""
    if isinstance(message_id, bool) or not str(message_id).isdigit() or not 0 < int(message_id) <= 2**63 - 1:
        raise ValidationError("شناسهٔ پیام گروه معتبر نیست.")
    record_id = StudioDelivery.objects.values_list("record_id", flat=True).get(pk=delivery_id)
    with transaction.atomic():
        record = _lock_record(record_id)
        job = StudioDelivery.objects.select_for_update().get(pk=delivery_id)
        if job.action != StudioDelivery.Action.PUBLISH or job.status != StudioDelivery.Status.UNCERTAIN:
            raise ValidationError("تنها ارسال نامشخص را می‌توان به پیام موجود متصل کرد.")
        # Without a verified date, use the original attempt time conservatively
        # for the 48-hour deletion window.
        created_at = sent_at or job.locked_at or job.created_at
        _map_message(record, job, int(message_id), created_at)
        return job


def _recover_stale_leases(now):
    cutoff = now - timedelta(seconds=max(90, int(getattr(settings, "STUDIO_DELIVERY_LOCK_SECONDS", 120))))
    stale = StudioDelivery.objects.filter(status=StudioDelivery.Status.SENDING, locked_at__lt=cutoff)
    stale.filter(action=StudioDelivery.Action.PUBLISH).update(
        status=StudioDelivery.Status.UNCERTAIN, last_error="worker_interrupted", updated_at=now,
    )
    stale.filter(action=StudioDelivery.Action.RETIRE).update(
        status=StudioDelivery.Status.RETRY, locked_at=None, lock_token=None,
        next_attempt_at=now, last_error="worker_interrupted", updated_at=now,
    )


def claim_delivery():
    now = timezone.now()
    _recover_stale_leases(now)
    # The compare-and-set also works on local SQLite, where select_for_update
    # does not provide row locks. No database transaction spans the HTTP call.
    for pk in StudioDelivery.objects.filter(status__in=READY, next_attempt_at__lte=now).values_list("pk", flat=True)[:20]:
        token = uuid.uuid4()
        changed = StudioDelivery.objects.filter(pk=pk, status__in=READY, next_attempt_at__lte=now).update(
            status=StudioDelivery.Status.SENDING, locked_at=now, lock_token=token,
            attempts=F("attempts") + 1, last_error="", updated_at=now,
        )
        if changed:
            return StudioDelivery.objects.select_related("record").get(pk=pk)
    return None


def _jpeg_bytes(record):
    with record.image.open("rb") as source, Image.open(source) as image:
        image.load()
        rgb = image.convert("RGB")
        try:
            rgb.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
            output = BytesIO()
            rgb.save(output, format="JPEG", quality=90, optimize=True)
            return output.getvalue()
        finally:
            rgb.close()


def _finish(job, outcome):
    return StudioDelivery.objects.filter(pk=job.pk, lock_token=job.lock_token).update(
        status=StudioDelivery.Status.SENT, outcome=outcome, sent_at=timezone.now(),
        locked_at=None, lock_token=None, last_error="", updated_at=timezone.now(),
    )


def _publish(job):
    record = StudioProduct.objects.get(pk=job.record_id)
    if record.status != StudioProduct.Status.AVAILABLE:
        _finish(job, "not_available")
        return
    photo = _jpeg_bytes(record)
    # A paused worker may resume after stale-lease recovery/manual action. Fence
    # the outbound send as well as its later database completion.
    cutoff = timezone.now() - timedelta(seconds=max(90, int(getattr(settings, "STUDIO_DELIVERY_LOCK_SECONDS", 120))))
    if not StudioDelivery.objects.filter(
        pk=job.pk, status=StudioDelivery.Status.SENDING, lock_token=job.lock_token,
        locked_at__gte=cutoff,
    ).exists():
        return
    message = studio_transport.send_photo(job.chat_id, photo, product_caption(record))
    # A malformed success is ambiguous: Telegram may already have the message.
    try:
        message_id = message["message_id"]
        if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id <= 0:
            raise ValueError
        if str(message["chat"]["id"]) != str(job.chat_id):
            raise ValueError
        created_at = datetime.fromtimestamp(message["date"], tz=datetime_timezone.utc)
        photos = message.get("photo", [])
        file_id = max(photos, key=lambda item: item.get("width", 0) * item.get("height", 0)).get("file_id", "") if photos else ""
    except (KeyError, TypeError, ValueError, OverflowError):
        raise studio_transport.TelegramDeliveryError("invalid_response", uncertain=True) from None
    with transaction.atomic():
        current = _lock_record(record.pk)
        leased = StudioDelivery.objects.select_for_update().get(pk=job.pk)
        if leased.lock_token != job.lock_token:
            return
        _map_message(current, leased, message_id, created_at, file_id)


def _retire(job):
    record = StudioProduct.objects.get(pk=job.record_id)
    if not job.message_id:
        raise studio_transport.TelegramDeliveryError("message_identity_missing")
    too_old = job.telegram_created_at and timezone.now() - job.telegram_created_at >= timedelta(hours=48)
    if not too_old:
        try:
            studio_transport.delete_message(job.chat_id, job.message_id)
        except studio_transport.TelegramDeliveryError as error:
            if error.code == "message_not_found":
                _finish(job, "already_absent")
                return
            if error.retryable or error.uncertain:
                raise
            # A permanent permission/age error should try the accepted visible
            # caption fallback. If that also fails, the queue shows the failure.
        else:
            _finish(job, "deleted")
            return
    if record.status == StudioProduct.Status.SOLD:
        label = "فروخته شد"
    elif record.status == StudioProduct.Status.DELETED:
        label = "حذف شد"
    else:
        label = "کشیده شد"
    try:
        studio_transport.edit_caption(job.chat_id, job.message_id, f"{label}\n{product_caption(record)}")
    except studio_transport.TelegramDeliveryError as error:
        if error.code == "message_not_found":
            _finish(job, "already_absent")
            return
        raise
    with transaction.atomic():
        current = _lock_record(record.pk)
        if current.status != record.status:
            # A withdrawal can follow a sale while the caption request is in
            # flight. Keep the newer terminal state queued instead of losing it.
            StudioDelivery.objects.filter(pk=job.pk, lock_token=job.lock_token).update(
                status=StudioDelivery.Status.RETRY, next_attempt_at=timezone.now(),
                locked_at=None, lock_token=None, updated_at=timezone.now(),
            )
        else:
            _finish(job, "caption_marked")


def _record_error(job, *, code, retryable=False, uncertain=False):
    safe_code = code if isinstance(code, str) and re.fullmatch(r"[a-z0-9_]{1,64}", code) else "delivery_error"
    max_attempts = max(1, int(getattr(settings, "STUDIO_DELIVERY_MAX_ATTEMPTS", 6)))
    # Deletion/caption editing is idempotent, so a lost response can be retried.
    if uncertain and job.action == StudioDelivery.Action.PUBLISH:
        status = StudioDelivery.Status.UNCERTAIN
    elif (retryable or uncertain) and job.attempts < max_attempts:
        status = StudioDelivery.Status.RETRY
    else:
        status = StudioDelivery.Status.FAILED
    wait = max(5, min(3600, 5 * 2 ** min(job.attempts, 9)), getattr(job, "retry_after", 0) or 0)
    updates = {"status": status, "last_error": safe_code,
               "next_attempt_at": timezone.now() + timedelta(seconds=wait), "updated_at": timezone.now()}
    if status != StudioDelivery.Status.UNCERTAIN:
        updates.update(locked_at=None, lock_token=None)
    StudioDelivery.objects.filter(pk=job.pk, lock_token=job.lock_token).update(**updates)
    logger.warning("studio delivery requires follow-up delivery_id=%s code=%s", job.pk, safe_code)


def process_next_delivery():
    """Process at most one due job, returning it or None. No live call on imports."""
    job = claim_delivery()
    if job is None:
        return None
    try:
        if job.action == StudioDelivery.Action.PUBLISH:
            _publish(job)
        else:
            _retire(job)
    except studio_transport.TelegramDeliveryError as error:
        job.retry_after = error.retry_after
        _record_error(job, code=error.code, retryable=error.retryable, uncertain=error.uncertain)
    except (OSError, Image.DecompressionBombError):
        _record_error(job, code="image_unavailable")
    except Exception:
        # Includes failure to persist an otherwise successful Telegram response.
        # Never print the exception; HTTP errors may contain a bot token.
        _record_error(job, code="delivery_interrupted", uncertain=True)
    job.refresh_from_db()
    return job
