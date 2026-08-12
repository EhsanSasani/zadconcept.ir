import html
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .models import LeadRequest


logger = logging.getLogger(__name__)
TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _text(value, *, limit):
    normalized = " ".join(str(value or "").split())
    if len(normalized) > limit:
        normalized = normalized[: limit - 1].rstrip() + "…"
    return html.escape(normalized) or "—"


def format_lead_request_message(lead):
    created_at = timezone.localtime(lead.created_at).strftime("%Y-%m-%d %H:%M")
    preferred_date = (
        lead.preferred_date.isoformat() if lead.preferred_date else "—"
    )
    product = lead.product.display_name if lead.product_id else "—"

    return "\n".join(
        (
            "🌿 <b>درخواست جدید از سایت ZAD</b>",
            "",
            f"👤 <b>نام:</b> {_text(lead.full_name, limit=160)}",
            f"📞 <b>موبایل:</b> <code>{_text(lead.mobile, limit=30)}</code>",
            f"🎯 <b>نوع درخواست:</b> {_text(lead.get_lead_type_display(), limit=80)}",
            f"🚚 <b>زمان تحویل:</b> {_text(lead.get_delivery_window_display(), limit=80)}",
            f"📅 <b>تاریخ انتخابی:</b> {_text(preferred_date, limit=30)}",
            f"📍 <b>مکان:</b> {_text(lead.event_location, limit=240)}",
            f"🎁 <b>محصول:</b> {_text(product, limit=200)}",
            f"📝 <b>توضیح:</b> {_text(lead.note, limit=1000)}",
            "",
            f"🌐 <b>صفحه مبدا:</b> {_text(lead.source_page, limit=300)}",
            f"🕒 <b>زمان ثبت:</b> <code>{created_at}</code>",
            f"🆔 <b>شناسه:</b> <code>{lead.pk}</code>",
        )
    )


def _send_via_relay(lead_id, lead, relay_url, relay_secret):
    payload = json.dumps(
        {"text": format_lead_request_message(lead)}
    ).encode("utf-8")
    request = Request(
        relay_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {relay_secret}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=settings.TELEGRAM_LEAD_TIMEOUT_SECONDS,
        ) as response:
            result = json.load(response)
        if result.get("ok") is True:
            return True
        logger.error(
            "Telegram relay rejected lead notification; lead_id=%s",
            lead_id,
        )
    except HTTPError as exc:
        logger.error(
            "Telegram relay HTTP error; lead_id=%s status=%s",
            lead_id,
            exc.code,
        )
    except (URLError, TimeoutError, OSError, ValueError):
        logger.exception(
            "Telegram relay notification failed; lead_id=%s",
            lead_id,
        )

    return False


def send_lead_request_notification(lead_id):
    relay_url = settings.TELEGRAM_LEAD_RELAY_URL
    relay_secret = settings.TELEGRAM_LEAD_RELAY_SECRET
    if relay_url or relay_secret:
        if not relay_url or not relay_secret:
            logger.warning(
                "Telegram lead relay is incomplete; lead_id=%s",
                lead_id,
            )
            return False
        try:
            lead = LeadRequest.objects.select_related("product").get(pk=lead_id)
        except LeadRequest.DoesNotExist:
            logger.error(
                "Telegram lead notification target is missing; lead_id=%s",
                lead_id,
            )
            return False
        return _send_via_relay(lead_id, lead, relay_url, relay_secret)

    token = settings.TELEGRAM_LEAD_BOT_TOKEN
    chat_id = settings.TELEGRAM_LEAD_CHAT_ID
    if not token or not chat_id:
        logger.warning(
            "Telegram lead notification is not configured; lead_id=%s",
            lead_id,
        )
        return False

    try:
        lead = LeadRequest.objects.select_related("product").get(pk=lead_id)
    except LeadRequest.DoesNotExist:
        logger.error("Telegram lead notification target is missing; lead_id=%s", lead_id)
        return False

    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": format_lead_request_message(lead),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    request = Request(
        TELEGRAM_SEND_MESSAGE_URL.format(token=token),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=settings.TELEGRAM_LEAD_TIMEOUT_SECONDS,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result.get("ok") is True:
            return True
        logger.error(
            "Telegram rejected lead notification; lead_id=%s error_code=%s",
            lead_id,
            result.get("error_code"),
        )
    except HTTPError as exc:
        logger.error(
            "Telegram lead notification HTTP error; lead_id=%s status=%s",
            lead_id,
            exc.code,
        )
    except (URLError, TimeoutError, OSError, ValueError):
        logger.exception("Telegram lead notification failed; lead_id=%s", lead_id)

    return False
