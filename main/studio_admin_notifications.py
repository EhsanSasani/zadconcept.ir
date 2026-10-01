"""Durable customer-safe Telegram photo notifications for Studio records."""
import re
import uuid
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.db.models import F
from django.utils import timezone
from PIL import Image

from . import studio_transport
from .models import StudioAdminNotification, StudioProduct


READY = (
    StudioAdminNotification.Status.PENDING,
    StudioAdminNotification.Status.RETRY,
)
NOTIFIED_SOURCES = {
    StudioProduct.Source.PORTAL,
    StudioProduct.Source.DASHBOARD,
    StudioProduct.Source.ADMIN,
}


def _admin_chat_id():
    value = str(getattr(settings, "TELEGRAM_STUDIO_ADMIN_CHAT_ID", "")).strip()
    if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        return None
    return int(value)


def customer_caption(record):
    return (
        f"کد: {record.factor_code}\n"
        f"قیمت: {record.price:,.0f} تومان\n"
        f"وضعیت: {record.get_status_display()}"
    )


def queue_admin_notification(record, event):
    """Create a DB outbox row; Telegram never runs inside the product request."""
    if record.source not in NOTIFIED_SOURCES:
        return None
    chat_id = _admin_chat_id()
    if chat_id is None:
        return None
    return StudioAdminNotification.objects.create(
        record=record,
        event=event,
        chat_id=chat_id,
        caption=customer_caption(record),
    )


def _recover_stale(now):
    cutoff = now - timedelta(
        seconds=max(90, int(getattr(settings, "STUDIO_DELIVERY_LOCK_SECONDS", 120)))
    )
    StudioAdminNotification.objects.filter(
        status=StudioAdminNotification.Status.SENDING,
        locked_at__lt=cutoff,
    ).update(
        status=StudioAdminNotification.Status.UNCERTAIN,
        last_error="worker_interrupted",
        updated_at=now,
    )


def claim_admin_notification():
    now = timezone.now()
    _recover_stale(now)
    due = StudioAdminNotification.objects.filter(
        status__in=READY,
        next_attempt_at__lte=now,
    ).values_list("pk", flat=True)[:20]
    for pk in due:
        token = uuid.uuid4()
        changed = StudioAdminNotification.objects.filter(
            pk=pk,
            status__in=READY,
            next_attempt_at__lte=now,
        ).update(
            status=StudioAdminNotification.Status.SENDING,
            locked_at=now,
            lock_token=token,
            attempts=F("attempts") + 1,
            last_error="",
            updated_at=now,
        )
        if changed:
            return StudioAdminNotification.objects.select_related(
                "record", "record__product",
            ).get(pk=pk)
    return None


def _jpeg_bytes(record):
    image = record.image
    if not image and record.product_id and record.product.cover_image:
        image = record.product.cover_image
    if not image:
        raise studio_transport.TelegramDeliveryError("invalid_payload")
    with image.open("rb") as source, Image.open(source) as opened:
        opened.load()
        rgb = opened.convert("RGB")
        try:
            rgb.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
            output = BytesIO()
            rgb.save(output, format="JPEG", quality=90, optimize=True)
            return output.getvalue()
        finally:
            rgb.close()


def _finish(job, message_id):
    StudioAdminNotification.objects.filter(
        pk=job.pk, lock_token=job.lock_token,
    ).update(
        status=StudioAdminNotification.Status.SENT,
        telegram_message_id=message_id,
        sent_at=timezone.now(),
        locked_at=None,
        lock_token=None,
        last_error="",
        updated_at=timezone.now(),
    )


def _record_error(job, error):
    max_attempts = max(1, int(getattr(settings, "STUDIO_DELIVERY_MAX_ATTEMPTS", 6)))
    if error.uncertain:
        status = StudioAdminNotification.Status.UNCERTAIN
    elif error.retryable and job.attempts < max_attempts:
        status = StudioAdminNotification.Status.RETRY
    else:
        status = StudioAdminNotification.Status.FAILED
    wait = max(
        5,
        min(3600, 5 * 2 ** min(job.attempts, 9)),
        error.retry_after or 0,
    )
    updates = {
        "status": status,
        "last_error": error.code,
        "next_attempt_at": timezone.now() + timedelta(seconds=wait),
        "updated_at": timezone.now(),
    }
    if status != StudioAdminNotification.Status.UNCERTAIN:
        updates.update(locked_at=None, lock_token=None)
    StudioAdminNotification.objects.filter(
        pk=job.pk, lock_token=job.lock_token,
    ).update(**updates)


def process_next_admin_notification():
    job = claim_admin_notification()
    if job is None:
        return None
    try:
        response = studio_transport.send_photo(
            job.chat_id,
            _jpeg_bytes(job.record),
            job.caption,
        )
        message_id = response["message_id"]
        if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id <= 0:
            raise studio_transport.TelegramDeliveryError(
                "invalid_response", uncertain=True,
            )
        _finish(job, message_id)
    except studio_transport.TelegramDeliveryError as error:
        _record_error(job, error)
    return StudioAdminNotification.objects.get(pk=job.pk)
