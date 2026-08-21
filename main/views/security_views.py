import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


security_logger = logging.getLogger("main.security")


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
