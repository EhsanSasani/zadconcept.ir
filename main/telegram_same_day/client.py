"""Bounded Bot API transport. Never surface token-bearing URLs/exceptions."""
import json
import re
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.core.files.base import ContentFile

MAX_IMAGE_BYTES = 20_000_000


class TelegramTransportError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(url, *, payload=None, headers=None, limit=65536):
    if urlsplit(url).scheme != "https":
        raise TelegramTransportError("https_required")
    request = Request(
        url, data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "User-Agent":
                 "Mozilla/5.0 (compatible; ZAD-Backend/1.0; +https://www.zadconcept.ir/)",
                 **(headers or {})},
    )
    try:
        with build_opener(NoRedirect).open(
            request, timeout=settings.TELEGRAM_SAME_DAY_TIMEOUT_SECONDS
        ) as response:
            data = response.read(limit + 1)
            if len(data) > limit:
                raise TelegramTransportError("response_too_large")
            return data
    except (URLError, OSError, ValueError):
        raise TelegramTransportError("telegram_request_failed") from None


def bot_api(method, payload):
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise TelegramTransportError("bot_token_missing")
    data = _request(f"https://api.telegram.org/bot{token}/{method}", payload=payload)
    try:
        result = json.loads(data)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise ValueError
        return result["result"]
    except (ValueError, KeyError, TypeError):
        raise TelegramTransportError("telegram_api_failed") from None


def download_photo(file_id):
    if not isinstance(file_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", file_id):
        raise TelegramTransportError("invalid_file_id")
    relay = settings.TELEGRAM_SAME_DAY_RELAY_URL
    if relay:
        if not settings.TELEGRAM_LEAD_RELAY_SECRET:
            raise TelegramTransportError("relay_secret_missing")
        data = _request(
            relay.rstrip("/") + "/same-day-file", payload={"file_id": file_id},
            headers={"Authorization": f"Bearer {settings.TELEGRAM_LEAD_RELAY_SECRET}"},
            limit=MAX_IMAGE_BYTES,
        )
    else:
        info = bot_api("getFile", {"file_id": file_id})
        path = info.get("file_path") if isinstance(info, dict) else None
        if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9_/-]+\.[A-Za-z0-9]+", path):
            raise TelegramTransportError("invalid_file_path")
        if path.startswith("/") or ".." in path:
            raise TelegramTransportError("invalid_file_path")
        data = _request(
            f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{path}",
            limit=MAX_IMAGE_BYTES,
        )
    return ContentFile(data, name="telegram.jpg")
