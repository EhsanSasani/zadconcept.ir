import re

from django.conf import settings


GOOGLE_TAG_ID_PATTERN = re.compile(r"^(?:G|GT|AW)-[A-Z0-9]+$")


def full_address_text(street, locality):
    """Return one consistent public address without duplicating the city."""

    street = (street or "").strip()
    locality = (locality or "").strip()

    if not locality:
        return street
    if not street:
        return locality

    normalized_street = street.lstrip("،, -")
    if normalized_street == locality or any(
        normalized_street.startswith(f"{locality}{separator}")
        for separator in ("،", ",", " ", "-")
    ):
        return street

    return f"{locality}، {street}"


def site_defaults(request):
    google_tag_id = settings.GOOGLE_TAG_ID.strip().upper()
    if not GOOGLE_TAG_ID_PATTERN.fullmatch(google_tag_id):
        google_tag_id = ""

    return {
        "site_url": settings.ZAD_SITE_URL,
        "site_call_href": f"tel:{settings.ZAD_PHONE_E164}",
        "site_phone_display": settings.ZAD_PHONE_DISPLAY,
        "site_telegram_url": settings.ZAD_TELEGRAM_URL,
        "site_telegram_display": settings.ZAD_TELEGRAM_DISPLAY,
        "site_bale_url": settings.ZAD_BALE_URL,
        "site_bale_display": settings.ZAD_BALE_DISPLAY,
        "site_instagram_url": settings.ZAD_INSTAGRAM_URL,
        "site_email": settings.ZAD_EMAIL,
        "site_opening_hours_text": settings.ZAD_OPENING_HOURS_TEXT,
        "site_response_time_text": settings.ZAD_RESPONSE_TIME_TEXT,
        "site_address_text": full_address_text(
            settings.ZAD_ADDRESS_STREET,
            settings.ZAD_ADDRESS_LOCALITY,
        ),
        "site_default_social_image": settings.ZAD_DEFAULT_SOCIAL_IMAGE,
        "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
        "bing_site_verification": settings.BING_SITE_VERIFICATION,
        "google_tag_id": google_tag_id,
        "top_notice_text": (
            "برای سفارش و هماهنگی سریع زاد، با شماره "
            f"{settings.ZAD_PHONE_DISPLAY} تماس بگیرید یا در تلگرام "
            f"{settings.ZAD_TELEGRAM_DISPLAY} پیام بدهید."
        ),
    }
