"""Manager-only recovery of private notifications, separate from group jobs."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import StudioAdminNotification
from .studio_access import require_studio_permission
from .studio_admin_notifications import reconcile_admin_notification, retry_admin_notification
from .studio_views import _base, _sort_state


ERROR_LABELS = {
    "invalid_payload": "تصویر یا مقصد معتبر نیست؛ تصویر محصول و تنظیم مقصد را بررسی کنید.",
    "configuration_error": "تنظیم اتصال یا مقصد کامل نیست.",
    "relay_unauthorized": "تنظیم دسترسی به رابط تلگرام نیازمند بررسی است.",
    "telegram_forbidden": "ربات به این گفت‌وگو دسترسی ندارد؛ شروع گفت‌وگو و مسدودنبودن ربات را بررسی کنید.",
    "telegram_unauthorized": "دسترسی ربات نیازمند بررسی است.",
    "telegram_bad_request": "تلگرام درخواست را نپذیرفت؛ تصویر و مقصد را بررسی کنید.",
    "rate_limited": "تلگرام درخواست کرده است ارسال کمی بعد انجام شود.",
    "telegram_server_error": "تلگرام موقتاً در دسترس نیست.",
    "transport_unavailable": "اتصال برقرار نشد؛ ارسال بعداً پیگیری می‌شود.",
    "transport_uncertain": "تأیید ارسال دریافت نشد؛ ابتدا وجود پیام را بررسی کنید.",
    "invalid_response": "تأیید معتبر دریافت نشد؛ ابتدا وجود پیام را بررسی کنید.",
    "worker_interrupted": "پردازشگر پیش از دریافت تأیید متوقف شد؛ ابتدا وجود پیام را بررسی کنید.",
}


@never_cache
@login_required(login_url="studio_login")
@require_http_methods(["GET", "POST"])
def admin_notifications(request):
    require_studio_permission(request)
    if request.method == "POST":
        require_studio_permission(request, "change_studioproduct")
        pk = request.POST.get("notification_id", "")
        if not pk.isascii() or not pk.isdecimal() or len(pk) > 19 or not 0 < int(pk) <= 2**63 - 1:
            return HttpResponseBadRequest("شناسهٔ اعلان معتبر نیست.")
        item = get_object_or_404(StudioAdminNotification, pk=int(pk))
        try:
            action = request.POST.get("action")
            if action == "retry":
                retry_admin_notification(item.pk, actor=request.user)
            elif action == "retry_absent":
                retry_admin_notification(item.pk, actor=request.user,
                                         confirmed_absent=request.POST.get("verified_absent") == "yes")
            elif action == "reconcile":
                message_id = request.POST.get("message_id", "")
                if not message_id.isascii() or not message_id.isdecimal() or len(message_id) > 16:
                    raise ValidationError("شناسهٔ عددی پیام را وارد کنید.")
                reconcile_admin_notification(item.pk, int(message_id), actor=request.user,
                                             verified=request.POST.get("verified") == "yes")
            else:
                raise ValidationError("اقدام معتبر نیست.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "پیگیری اعلان ثبت شد؛ هیچ ارسال مستقیمی از این صفحه انجام نمی‌شود.")
        return redirect("studio_admin_notifications")

    qs = StudioAdminNotification.objects.select_related("record", "record__florist")
    counts = dict(qs.values_list("status").annotate(total=Count("pk")))
    state = request.GET.get("status", "")
    if state in StudioAdminNotification.Status.values:
        qs = qs.filter(status=state)
    query = request.GET.get("q", "").strip()[:40]
    if query:
        qs = qs.filter(record__factor_code__icontains=query)
    fields = {"factor": "record__factor_code", "event": "event", "status": "status", "attempts": "attempts", "date": "created_at"}
    table_sort = _sort_state(request, fields, "date")
    qs = qs.order_by(("-" if table_sort["direction"] == "desc" else "") + fields[table_sort["key"]], "-pk")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    for item in page:
        item.error_label = ERROR_LABELS.get(item.last_error, "این اعلان نیازمند بررسی است.") if item.last_error else ""
    return render(request, "main/studio/admin_notifications.html", {
        **_base(request, "deliveries"), "page": page, "table_sort": table_sort,
        "status_choices": StudioAdminNotification.Status.choices,
        "waiting": sum(counts.get(key, 0) for key in ("PENDING", "SENDING", "RETRY")),
        "needs_review": sum(counts.get(key, 0) for key in ("FAILED", "UNCERTAIN")),
        "delivered": counts.get("SENT", 0),
    })
