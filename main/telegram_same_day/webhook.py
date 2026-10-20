import hmac
import json
import logging

from django.conf import settings
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_POST

from .client import TelegramTransportError
from .service import InvalidSource, SyncConfigurationError, PendingPortalIdentity, process_update
from .validation import InvalidUpdate, validate_update

logger = logging.getLogger("main.telegram_same_day")
MAX_UPDATE_BYTES = 128 * 1024


@csrf_exempt
@require_POST
@sensitive_variables()
def telegram_webhook(request):
    expected = settings.TELEGRAM_WEBHOOK_SECRET
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
        return JsonResponse({"ok": False}, status=403)
    if request.content_type != "application/json":
        return JsonResponse({"ok": False}, status=415)
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_UPDATE_BYTES:
            raise InvalidUpdate("too_large")
        body = request.read(MAX_UPDATE_BYTES + 1)
        if len(body) > MAX_UPDATE_BYTES:
            raise InvalidUpdate("too_large")
        update = json.loads(body)
        kind, message = validate_update(update)
    except (ValueError, UnicodeDecodeError, RequestDataTooBig):
        return JsonResponse({"ok": False, "error": "Invalid update"}, status=400)
    if kind is None:
        return JsonResponse({"ok": True, "result": "ignored"})
    try:
        result = process_update(kind, message, update["update_id"])
    except PendingPortalIdentity as pending:
        from ..studio_pending_replies import retain_pending_reply
        try:
            retain_pending_reply(update_id=update['update_id'],kind=kind,message=message,delivery_id=pending.delivery_id)
        except (DatabaseError, ValidationError):
            return JsonResponse({'ok':False,'error':'Retry required'},status=503)
        logger.warning('Telegram command retained pending reconciliation update_id=%s delivery_id=%s',update['update_id'],pending.delivery_id)
        return JsonResponse({'ok':True,'result':'awaiting_message_reconciliation'})
    except InvalidSource:
        logger.warning("invalid Telegram source rejected update_id=%s chat_id=%s",
                       update["update_id"], message["chat"]["id"])
        return JsonResponse({"ok": False}, status=403)
    except (TelegramTransportError, SyncConfigurationError, DatabaseError, OSError, ValidationError) as exc:
        # No exception formatting: transport URLs may contain the bot token.
        logger.error("Telegram sync retry required update_id=%s chat_id=%s message_id=%s error_type=%s",
                     update["update_id"], message["chat"]["id"], message["message_id"],type(exc).__name__)
        return JsonResponse({"ok": False, "error": "Retry required"}, status=503)
    return JsonResponse({"ok": True, **result} if isinstance(result, dict) else {"ok": True, "result": result})
