"""HTTP adapter for lead submissions."""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..forms import LeadRequestForm
from ..services.leads import is_rate_limited, save_lead


def _remote_address(request):
    # Nginx overwrites X-Real-IP before proxying through the private Unix socket.
    return request.META.get("HTTP_X_REAL_IP") or request.META.get(
        "REMOTE_ADDR", "unknown"
    )


@require_POST
def submit_lead_request(request):
    include_event_fields = request.POST.get("lead_type") == "event"
    form = LeadRequestForm(request.POST, include_event_fields=include_event_fields)

    next_url = (
        request.POST.get("next")
        or request.META.get("HTTP_REFERER")
        or reverse("index")
    )
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
    ):
        next_url = reverse("index")

    if is_rate_limited(_remote_address(request)):
        messages.error(
            request,
            "تعداد درخواست‌ها زیاد است؛ چند دقیقه دیگر دوباره تلاش کنید.",
        )
        return redirect(next_url)

    if form.is_valid():
        save_lead(form, source_page=request.POST.get("source_page", ""))
        messages.success(
            request,
            "Your request has been submitted. zad will contact you soon.",
            extra_tags="lead-success",
        )
    else:
        messages.error(request, "Please complete the form correctly and try again.")

    return redirect(next_url)
