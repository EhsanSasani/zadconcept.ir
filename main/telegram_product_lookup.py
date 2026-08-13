import hmac
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Product


def _is_authorized(request):
    expected = getattr(settings, "TELEGRAM_LEAD_RELAY_SECRET", "")
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "

    if not expected or not authorization.startswith(prefix):
        return False

    provided = authorization[len(prefix) :].strip()
    return bool(provided) and hmac.compare_digest(provided, expected)


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

    product_image = next(iter(product.gallery_images.all()), None)
    if product_image is None or not product_image.image:
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
                "image_url": request.build_absolute_uri(product_image.image.url),
            },
        }
    )
