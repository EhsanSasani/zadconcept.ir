import hmac
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Product, TelegramBotUser


def _is_authorized(request):
    expected = getattr(settings, "TELEGRAM_LEAD_RELAY_SECRET", "")
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "

    if not expected or not authorization.startswith(prefix):
        return False

    provided = authorization[len(prefix) :].strip()
    return bool(provided) and hmac.compare_digest(provided, expected)


def _telegram_user_id(payload):
    if "telegram_user_id" not in payload:
        raise ValueError

    raw_value = payload.get("telegram_user_id")
    if isinstance(raw_value, bool):
        raise ValueError

    value = str(raw_value).strip()
    if not value or len(value) > 20:
        raise ValueError

    try:
        user_id = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError from error

    if user_id <= 0:
        raise ValueError

    return user_id


@csrf_exempt
@require_POST
def telegram_product_lookup(request):
    if not _is_authorized(request):
        return JsonResponse({"ok": False, "error": "Unauthorized"}, status=401)

    if len(request.body) > 1024:
        return JsonResponse({"ok": False, "error": "Request too large"}, status=400)

    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    try:
        telegram_user_id = _telegram_user_id(payload)
    except ValueError:
        return JsonResponse(
            {"ok": False, "error": "Invalid Telegram user ID"},
            status=400,
        )

    if not TelegramBotUser.objects.filter(
        telegram_user_id=telegram_user_id,
        is_active=True,
        can_lookup_products=True,
    ).exists():
        return JsonResponse(
            {"ok": False, "error": "Telegram user is not allowed"},
            status=403,
        )

    code = payload.get("code", "")
    code = code.strip() if isinstance(code, str) else ""

    if not code or len(code) > 40:
        return JsonResponse(
            {"ok": False, "error": "Invalid product code"},
            status=400,
        )

    product = (
        Product.objects.prefetch_related("gallery_images")
        .filter(product_code__iexact=code)
        .first()
    )

    if product is None:
        return JsonResponse(
            {"ok": False, "error": "Product not found"},
            status=404,
        )

    gallery_image = next(
        (
            product_image.image
            for product_image in product.gallery_images.all()
            if product_image.image
        ),
        None,
    )
    image = gallery_image or product.cover_image
    if not image:
        return JsonResponse(
            {"ok": False, "error": "Product image not found"},
            status=404,
        )

    return JsonResponse(
        {
            "ok": True,
            "product": {
                "code": product.product_code,
                "name": product.display_name,
                "price_display": product.display_price,
                "image_url": request.build_absolute_uri(image.url),
            },
        }
    )
