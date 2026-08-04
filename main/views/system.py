"""Operational and crawler-facing endpoints."""

import json
import logging
import re

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

security_logger = logging.getLogger("main.security")
INDEXNOW_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")


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
    response = HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


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


@csrf_exempt
@require_POST
def csp_report(request):
    if len(request.body) > 64 * 1024:
        return HttpResponse(status=413)

    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)

    report = payload.get("csp-report", payload) if isinstance(payload, dict) else {}
    security_logger.warning(
        "CSP violation document=%s directive=%s blocked=%s",
        report.get("document-uri", ""),
        report.get("violated-directive", report.get("effective-directive", "")),
        report.get("blocked-uri", ""),
    )
    return HttpResponse(status=204)


def custom_404(request, exception):
    context = {
        "meta_title": "صفحه پیدا نشد | ZAD",
        "meta_description": "صفحه مورد نظر پیدا نشد.",
        "robots_content": "noindex,nofollow",
        "page_type": "error-404",
        "is_home": True,
    }
    return render(request, "404.html", context, status=404)
