import re

from django.conf import settings
from django.http import Http404, HttpResponse
from django.urls import reverse


def robots_txt(request):
    lines = [
        "# Search and answer-engine crawlers",
        "User-agent: Googlebot",
        "User-agent: Bingbot",
        "User-agent: OAI-SearchBot",
        "User-agent: ChatGPT-User",
        "User-agent: PerplexityBot",
        "User-agent: Claude-SearchBot",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /auth/",
        "Disallow: /search/",
        "Disallow: /lead-request/",
        "Disallow: /csp-report/",
        "",
        "# Model-training crawlers are handled separately from search crawlers",
        "User-agent: GPTBot",
        "User-agent: ClaudeBot",
        "User-agent: Google-Extended",
        "User-agent: CCBot",
        "Disallow: /",
        "",
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /auth/",
        "Disallow: /search/",
        "Disallow: /lead-request/",
        "Disallow: /csp-report/",
        f"Sitemap: {settings.ZAD_SITE_URL}{reverse('sitemap')}",
    ]

    response = HttpResponse(
        "\n".join(lines),
        content_type="text/plain; charset=utf-8",
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


INDEXNOW_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def indexnow_key(request, key):
    configured_key = settings.INDEXNOW_KEY
    if (
        request.method not in {"GET", "HEAD"}
        or not configured_key
        or not INDEXNOW_KEY_PATTERN.fullmatch(configured_key)
        or key != configured_key
    ):
        raise Http404("IndexNow key not found")

    response = HttpResponse(configured_key, content_type="text/plain; charset=utf-8")
    response.headers["Cache-Control"] = "public, max-age=86400"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
