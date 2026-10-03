"""Durable customer-safe Telegram photo notifications for Studio records."""
import re
import uuid
import logging
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, F, OuterRef
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
logger = logging.getLogger(__name__)


def admin_notifications_enabled():
    return getattr(settings, "STUDIO_ADMIN_NOTIFICATIONS_ENABLED", False) is True


def _database(record):
    return record._state.db or "default"


def _lease_cutoff(now=None):
    return (now or timezone.now()) - timedelta(
        seconds=max(90, int(getattr(settings, "STUDIO_DELIVERY_LOCK_SECONDS", 120)))
    )


def _admin_chat_id():
    value = str(getattr(settings, "TELEGRAM_STUDIO_ADMIN_CHAT_ID", "")).strip()
    if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        return None
    number = int(value)
    # Invalid runtime configuration must not overflow the DB while saving a product.
    return number if number <= 2**63 - 1 else None


def customer_caption(record):
    return (
        f"کد: {record.factor_code}\n"
        f"قیمت: {record.price:,.0f} تومان\n"
        f"وضعیت: {record.get_status_display()}"
    )


def queue_admin_notification(record, event):
    """Create a DB outbox row; Telegram never runs inside the product request."""
    if not admin_notifications_enabled():
        return None
    if record.source not in NOTIFIED_SOURCES:
        return None
    chat_id = _admin_chat_id()
    if chat_id is None:
        return None
    return StudioAdminNotification.objects.using(_database(record)).create(
        record=record,
        event=event,
        chat_id=chat_id,
        caption=customer_caption(record),
    )


def _recover_stale(now):
    cutoff = _lease_cutoff(now)
    StudioAdminNotification.objects.filter(
        status=StudioAdminNotification.Status.SENDING,
        locked_at__lt=cutoff,
    ).update(
        status=StudioAdminNotification.Status.UNCERTAIN,
        last_error="worker_interrupted",
        updated_at=now,
    )


def claim_admin_notification():
    if not admin_notifications_enabled():
        return None
    now = timezone.now()
    _recover_stale(now)
    older_unresolved = StudioAdminNotification.objects.filter(
        record_id=OuterRef("record_id"), pk__lt=OuterRef("pk"),
        status__in=[*READY, StudioAdminNotification.Status.SENDING, StudioAdminNotification.Status.UNCERTAIN],
    )
    due = StudioAdminNotification.objects.annotate(
        has_older_unresolved=Exists(older_unresolved),
    ).filter(
        status__in=READY,
        next_attempt_at__lte=now,
        has_older_unresolved=False,
    ).values_list("pk", flat=True)[:20]
    for pk in due:
        token = uuid.uuid4()
        # Recovery can requeue an older event after the candidate query ran.
        # Recheck ordering in the same statement that acquires the lease.
        changed = StudioAdminNotification.objects.annotate(
            has_older_unresolved=Exists(older_unresolved),
        ).filter(
            pk=pk,
            status__in=READY,
            next_attempt_at__lte=now,
            has_older_unresolved=False,
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
    try:
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
    except (OSError, ValueError, Image.DecompressionBombError):
        # One bad private-notification image must never stop the group delivery loop.
        # Do not log a storage exception: remote storage URLs may carry credentials.
        raise studio_transport.TelegramDeliveryError("invalid_payload") from None


def _finish(job, message_id):
    StudioAdminNotification.objects.filter(
        pk=job.pk, lock_token=job.lock_token,
        status__in=[StudioAdminNotification.Status.SENDING, StudioAdminNotification.Status.UNCERTAIN],
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
        pk=job.pk, lock_token=job.lock_token, status=StudioAdminNotification.Status.SENDING,
    ).update(**updates)
    logger.warning("studio private notification requires follow-up notification_id=%s code=%s", job.pk, error.code)


def _can_manage(actor):
    if not getattr(actor, "is_active", False) or not actor.has_perm("main.change_studioproduct"):
        raise PermissionDenied
    if not admin_notifications_enabled():
        raise ValidationError("اعلان خصوصی مدیر غیرفعال است؛ ارسال دوباره انجام نمی‌شود.")


def _audit_recovery(job, actor, action):
    LogEntry.objects.db_manager(job._state.db or "default").log_actions(
        user_id=actor.pk,
        queryset=StudioAdminNotification.objects.using(job._state.db or "default").filter(pk=job.pk),
        action_flag=CHANGE,
        change_message=[{"changed": {"name": "private notification", "object": str(job.pk), "fields": [action]}}],
    )


def retry_admin_notification(notification_id, *, actor, confirmed_absent=False):
    """Explicit recovery; ambiguous sends need a human check and an expired lease."""
    _can_manage(actor)
    with transaction.atomic():
        job = StudioAdminNotification.objects.select_for_update().get(pk=notification_id)
        if job.chat_id != _admin_chat_id():
            raise ValidationError("مقصد این اعلان با تنظیم فعلی یکسان نیست؛ تنظیم مقصد را بررسی کنید.")
        if job.status == StudioAdminNotification.Status.UNCERTAIN:
            if confirmed_absent is not True:
                raise ValidationError("ابتدا نبودن پیام همین فاکتور و وضعیت را در گفت‌وگوی خصوصی تأیید کنید.")
            if job.locked_at and job.locked_at > _lease_cutoff():
                raise ValidationError("مهلت ارسال قبلی هنوز تمام نشده است؛ کمی بعد دوباره بررسی کنید.")
        elif job.status not in {StudioAdminNotification.Status.FAILED, StudioAdminNotification.Status.RETRY}:
            raise ValidationError("این اعلان قابل ارسال دوباره نیست.")
        if job.telegram_message_id:
            raise ValidationError("پیام این اعلان قبلاً ثبت شده است.")
        if StudioAdminNotification.objects.filter(
            record_id=job.record_id, pk__gt=job.pk,
            status__in=[StudioAdminNotification.Status.SENT, StudioAdminNotification.Status.SENDING,
                        StudioAdminNotification.Status.UNCERTAIN],
        ).exists():
            raise ValidationError("اعلان جدیدتری ارسال شده یا نتیجهٔ ارسال آن در حال بررسی است؛ پیام قدیمی را دوباره ارسال نکنید.")
        job.status = StudioAdminNotification.Status.PENDING
        job.next_attempt_at = timezone.now()
        job.attempts, job.last_error = 0, ""
        job.locked_at = job.lock_token = None
        job.save(update_fields=["status", "next_attempt_at", "attempts", "last_error", "locked_at", "lock_token", "updated_at"])
        _audit_recovery(job, actor, "retry after verified absence" if confirmed_absent else "retry failed notification")
        return job


def reconcile_admin_notification(notification_id, message_id, *, actor, verified):
    """Attach a human-verified existing private photo; never send another message."""
    _can_manage(actor)
    if verified is not True or isinstance(message_id, bool) or not isinstance(message_id, int) or not 0 < message_id <= 2**53 - 1:
        raise ValidationError("پیام همین فاکتور و وضعیت را بررسی و شناسهٔ عددی معتبر وارد کنید.")
    with transaction.atomic():
        job = StudioAdminNotification.objects.select_for_update().get(pk=notification_id)
        if job.status != StudioAdminNotification.Status.UNCERTAIN or job.telegram_message_id:
            raise ValidationError("فقط اعلان نامشخص و بدون پیام قابل اتصال است.")
        if job.chat_id != _admin_chat_id():
            raise ValidationError("مقصد این اعلان با تنظیم فعلی یکسان نیست؛ تنظیم مقصد را بررسی کنید.")
        if StudioAdminNotification.objects.exclude(pk=job.pk).filter(chat_id=job.chat_id, telegram_message_id=message_id).exists():
            raise ValidationError("این پیام قبلاً به اعلان دیگری متصل شده است.")
        job.status, job.telegram_message_id = StudioAdminNotification.Status.SENT, message_id
        job.sent_at, job.last_error = timezone.now(), ""
        job.locked_at = job.lock_token = None
        job.save(update_fields=["status", "telegram_message_id", "sent_at", "last_error", "locked_at", "lock_token", "updated_at"])
        _audit_recovery(job, actor, "reconciled verified existing private message")
        return job


def process_next_admin_notification():
    job = claim_admin_notification()
    if job is None:
        return None
    try:
        photo = _jpeg_bytes(job.record)
        if not StudioAdminNotification.objects.filter(
            pk=job.pk, status=StudioAdminNotification.Status.SENDING,
            lock_token=job.lock_token, locked_at__gte=_lease_cutoff(),
        ).exists():
            return StudioAdminNotification.objects.get(pk=job.pk)
        response = studio_transport.send_photo(
            job.chat_id,
            photo,
            job.caption,
        )
        message_id = response.get("message_id") if isinstance(response, dict) else None
        if isinstance(message_id, bool) or not isinstance(message_id, int) or not 0 < message_id <= 2**53 - 1:
            raise studio_transport.TelegramDeliveryError(
                "invalid_response", uncertain=True,
            )
        _finish(job, message_id)
    except studio_transport.TelegramDeliveryError as error:
        _record_error(job, error)
    return StudioAdminNotification.objects.get(pk=job.pk)
