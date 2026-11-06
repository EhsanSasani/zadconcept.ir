"""Validate staff form return locations; never use these as authorization."""
from urllib.parse import urlsplit

from django.urls import Resolver404, resolve, reverse

PRODUCT_RETURN_ROUTES = frozenset({
    "studio_products", "studio_metric", "studio_florist_profile",
    "studio_product_detail", "studio_dashboard",
})


def return_location(request, fallback, allowed=None):
    value = request.POST.get("return_to", "")
    if (not isinstance(value, str) or not value.startswith("/") or value.startswith("//")
            or len(value) > 2048 or "\\" in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        return reverse(fallback)
    try:
        parts = urlsplit(value)
        if parts.scheme or parts.netloc or parts.fragment:
            return reverse(fallback)
        match = resolve(parts.path)
    except (ValueError, Resolver404):
        return reverse(fallback)
    return value if match.url_name in (allowed or {fallback}) else reverse(fallback)
