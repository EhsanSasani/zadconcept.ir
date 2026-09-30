"""Bounded, private Telegram transport for the studio delivery worker.

Only the configured ready-products group is reachable. A lost ``sendPhoto``
response is deliberately uncertain: the outbox must reconcile it, not resend
it automatically and create a second public post.
"""

import base64
import json
import re
import secrets
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from django.conf import settings

from .telegram_same_day.client import NoRedirect

MAX_PHOTO_BYTES = 10_000_000
MAX_RESPONSE_BYTES = 65_536
MAX_CAPTION_UNITS = 1024
SAFE_ERROR_CODES = frozenset({
    "configuration_error", "invalid_payload", "relay_unauthorized",
    "rate_limited", "telegram_forbidden", "telegram_unauthorized",
    "telegram_bad_request", "telegram_server_error", "message_not_found",
    "message_cannot_be_deleted", "message_not_modified", "invalid_response",
    "transport_uncertain", "transport_unavailable",
})


class TelegramDeliveryError(Exception):
    """Contains only safe diagnostics, never raw URLs or Telegram descriptions."""

    def __init__(self, code, *, retryable=False, uncertain=False, retry_after=None):
        self.code = code if isinstance(code, str) and code in SAFE_ERROR_CODES else "invalid_response"
        self.uncertain = bool(uncertain)
        self.retryable = bool(retryable) and not self.uncertain
        self.retry_after = _retry_after(retry_after)
        super().__init__(self.code)


def _retry_after(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return min(max(number, 1), 86_400)


def _chat_id(value):
    value = str(value).strip()
    if not re.fullmatch(r"-[1-9][0-9]{0,19}", value):
        raise TelegramDeliveryError("invalid_payload")
    configured = str(getattr(settings, "TELEGRAM_SAME_DAY_GROUP_ID", "")).strip()
    if not re.fullmatch(r"-[1-9][0-9]{0,19}", configured):
        raise TelegramDeliveryError("configuration_error")
    if value != configured:
        raise TelegramDeliveryError("invalid_payload")
    return value


def _caption(value):
    if not isinstance(value, str):
        raise TelegramDeliveryError("invalid_payload")
    try:
        length = len(value.encode("utf-16-le")) // 2
    except UnicodeError:
        raise TelegramDeliveryError("invalid_payload") from None
    if not value.strip() or length > MAX_CAPTION_UNITS:
        raise TelegramDeliveryError("invalid_payload")
    return value


def _message_id(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= 2**53 - 1:
        raise TelegramDeliveryError("invalid_payload")
    return value


def _photo(value):
    if not isinstance(value, (bytes, bytearray)) or not 5 <= len(value) <= MAX_PHOTO_BYTES:
        raise TelegramDeliveryError("invalid_payload")
    if not value.startswith(b"\xff\xd8\xff") or not value.endswith(b"\xff\xd9"):
        raise TelegramDeliveryError("invalid_payload")
    return bytes(value)


def _unclear_response(method, code="invalid_response"):
    return TelegramDeliveryError(
        code, uncertain=method == "sendPhoto", retryable=method != "sendPhoto",
    )


def _telegram_error(status, result):
    code = result.get("error_code", status)
    description = str(result.get("description", "")).lower()
    parameters = result.get("parameters")
    retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
    if code == 429 or status == 429:
        return TelegramDeliveryError("rate_limited", retryable=True, retry_after=retry_after)
    if code == 401:
        return TelegramDeliveryError("telegram_unauthorized")
    if code == 403:
        return TelegramDeliveryError("telegram_forbidden")
    if code == 400:
        if "message is not modified" in description:
            return TelegramDeliveryError("message_not_modified")
        if "message to delete not found" in description or "message to edit not found" in description:
            return TelegramDeliveryError("message_not_found")
        if "message can't be deleted" in description or "message cannot be deleted" in description:
            return TelegramDeliveryError("message_cannot_be_deleted")
        return TelegramDeliveryError("telegram_bad_request")
    if isinstance(code, int) and 500 <= code <= 599:
        return TelegramDeliveryError("telegram_server_error", retryable=True)
    return TelegramDeliveryError("telegram_bad_request")


def _multipart(payload, photo):
    boundary = "zad-studio-" + secrets.token_hex(20)
    chunks = []
    for key, value in payload.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
            f'{value}\r\n'.encode("utf-8")
        )
    chunks.extend([
        f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="product.jpg"\r\n'
        'Content-Type: image/jpeg\r\n\r\n'.encode("ascii"),
        photo,
        f"\r\n--{boundary}--\r\n".encode("ascii"),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _read_response(response, method):
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise _unclear_response(method) from None
    try:
        result = json.loads(data)
    except (ValueError, UnicodeError):
        raise _unclear_response(method) from None
    if not isinstance(result, dict):
        raise _unclear_response(method) from None
    return result


def _request(method, payload, photo=None):
    relay = str(getattr(settings, "TELEGRAM_SAME_DAY_RELAY_URL", "")).strip()
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ZAD-Studio/1.0; +https://www.zadconcept.ir/)",
    }
    if relay:
        try:
            parts = urlsplit(relay)
        except ValueError:
            raise TelegramDeliveryError("configuration_error") from None
        secret = str(getattr(settings, "TELEGRAM_LEAD_RELAY_SECRET", "")).strip()
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or not secret):
            raise TelegramDeliveryError("configuration_error")
        url = relay.rstrip("/") + "/studio-delivery"
        relay_payload = {"method": method, **payload}
        if photo is not None:
            relay_payload["photo_base64"] = base64.b64encode(photo).decode("ascii")
        body = json.dumps(relay_payload, ensure_ascii=False).encode("utf-8")
        headers.update({"Authorization": f"Bearer {secret}", "Content-Type": "application/json"})
    else:
        token = str(getattr(settings, "TELEGRAM_BOT_TOKEN", "")).strip()
        # A token is a credential, never a caller-supplied URL path.
        if not re.fullmatch(r"[A-Za-z0-9:_-]{1,256}", token):
            raise TelegramDeliveryError("configuration_error")
        url = f"https://api.telegram.org/bot{token}/{method}"
        if photo is not None:
            body, headers["Content-Type"] = _multipart(payload, photo)
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
    try:
        timeout = float(getattr(settings, "STUDIO_TELEGRAM_TIMEOUT_SECONDS", 35))
        if not 1 <= timeout <= 120:
            raise ValueError
        request = Request(url, data=body, headers=headers, method="POST")
    except (ValueError, TypeError):
        raise TelegramDeliveryError("configuration_error") from None
    try:
        try:
            response = build_opener(NoRedirect).open(request, timeout=timeout)
        except HTTPError as error:
            # urllib raises before parsing Telegram's useful 400/403/429 envelope.
            # Its exception string contains the bot token; use only its response.
            response = error
        with response:
            status = response.status
            try:
                result = _read_response(response, method)
            except TelegramDeliveryError:
                if status == 429:
                    raise TelegramDeliveryError(
                        "rate_limited", retryable=True,
                        retry_after=response.headers.get("Retry-After") if response.headers else None,
                    ) from None
                raise
    except (URLError, OSError, ValueError, HTTPException):
        raise _unclear_response(
            method, "transport_uncertain" if method == "sendPhoto" else "transport_unavailable",
        ) from None
    if result.get("ok") is True and 200 <= status <= 299:
        value = result.get("result")
        if method == "sendPhoto":
            if (not isinstance(value, dict) or isinstance(value.get("message_id"), bool)
                    or not isinstance(value.get("message_id"), int) or value["message_id"] <= 0
                    or not isinstance(value.get("chat"), dict)
                    or str(value["chat"].get("id")) != payload["chat_id"]):
                raise _unclear_response(method)
        elif method == "deleteMessage" and value is not True:
            raise _unclear_response(method)
        elif method == "editMessageCaption" and not (value is True or isinstance(value, dict)):
            raise _unclear_response(method)
        return value
    if result.get("ok") is not False:
        raise _unclear_response(method)
    if relay:
        error_code = result.get("error")
        if (not isinstance(error_code, str) or error_code not in SAFE_ERROR_CODES
                or not isinstance(result.get("retryable"), bool)
                or not isinstance(result.get("uncertain"), bool)):
            raise _unclear_response(method)
        error = TelegramDeliveryError(
            error_code, retryable=result["retryable"], uncertain=result["uncertain"],
            retry_after=result.get("retry_after"),
        )
    else:
        code = result.get("error_code")
        if status != 429 and (isinstance(code, bool) or not isinstance(code, int)
                              or not 400 <= code <= 599):
            raise _unclear_response(method)
        error = _telegram_error(status, result)
    if method == "deleteMessage" and error.code == "message_not_found":
        return True
    if method == "editMessageCaption" and error.code == "message_not_modified":
        return True
    raise error from None


def send_photo(chat_id, photo_bytes, caption):
    return _request("sendPhoto", {"chat_id": _chat_id(chat_id), "caption": _caption(caption)}, _photo(photo_bytes))


def delete_message(chat_id, message_id):
    return _request("deleteMessage", {"chat_id": _chat_id(chat_id), "message_id": _message_id(message_id)})


def edit_caption(chat_id, message_id, caption):
    return _request("editMessageCaption", {
        "chat_id": _chat_id(chat_id), "message_id": _message_id(message_id), "caption": _caption(caption),
    })
