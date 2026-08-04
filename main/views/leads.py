"""HTTP adapter for lead submissions."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..forms import LeadRequestForm
from ..services.leads import is_rate_limited, save_lead
from .support import _default_context


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
            "درخواست شما ثبت شد؛ تیم زاد به‌زودی با شما تماس می‌گیرد.",
            extra_tags="lead-success",
        )
        return redirect(next_url)

    context = _default_context(
        request,
        page_type="lead-error",
        active_nav="",
        meta_title="اصلاح درخواست هماهنگی | زاد",
        meta_description="اصلاح اطلاعات فرم درخواست هماهنگی زاد.",
        suppress_default_hero=True,
        is_indexable=False,
    )
    context.update(
        {
            "lead_form": form,
            "lead_default_type": request.POST.get("lead_type") or "flower",
            "lead_next_url": next_url,
            "lead_source_page": request.POST.get("source_page", ""),
        }
    )
    return render(request, "lead_form_invalid.html", context, status=422)
