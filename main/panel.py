"""Shared entry and navigation; workspace choice never grants permissions."""
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from django.views.defaults import permission_denied

from .studio_access import can_manage_studio, can_use_sales, can_use_procurement, get_active_florist

SESSION_KEY = "zad_workspace"


def workspaces(user):
    choices = []
    for key, label, description, route, allowed in (
        ("studio", "مدیریت", "نمای کلی امروز، عملکرد تیم و گزارش‌ها", "studio_dashboard", can_manage_studio(user)),
        ("sales", "فروش", "موجودی، ثبت فروش و پیگیری محصولات", "sales_home", can_use_sales(user)),
        ("team", "فلوریست", "ثبت محصول، کارنامه و فضای شخصی شما", "team_home", bool(get_active_florist(user))),
        ("procurement", "خرید و دورریز", "کالاها، فاکتورهای خرید و دورریز روزانه", "procurement_home", can_use_procurement(user)),
    ):
        if allowed:
            choices.append({"key": key, "label": label, "description": description, "url": reverse(route)})
    return choices


def navigation(request):
    if not request.path.startswith(("/panel/", "/studio/", "/team/", "/sales/", "/procurement/")):
        return {}
    choices = workspaces(request.user)
    current = next((item for item in choices if request.path.startswith(item["url"])), None)
    return {"panel_workspaces": choices, "panel_current": current,
            "panel_multiple": len(choices) > 1}


@never_cache
@require_GET
def home(request):
    if not request.user.is_authenticated:
        return redirect_to_login(reverse("panel_home"), reverse("studio_login"))
    choices = workspaces(request.user)
    preferred = request.session.get(SESSION_KEY)
    selected = next((item for item in choices if item["key"] == preferred), None)
    if preferred and selected is None:
        request.session.pop(SESSION_KEY, None)
    if request.GET.get("choose") != "1":
        if len(choices) == 1:
            return redirect(choices[0]["url"])
    return render(request, "main/pages/panel/home.html", {
        "choices": choices, "selected": selected,
    })


@never_cache
@require_POST
def select(request):
    if not request.user.is_authenticated:
        return redirect_to_login(reverse("panel_home"), reverse("studio_login"))
    selected = next((item for item in workspaces(request.user)
                     if item["key"] == request.POST.get("workspace")), None)
    if selected is None:
        raise PermissionDenied
    request.session[SESSION_KEY] = selected["key"]
    return redirect(selected["url"])


@never_cache
def forbidden(request, exception=None):
    if not request.path.startswith(("/panel/", "/studio/", "/team/", "/sales/", "/procurement/")):
        return permission_denied(request, exception)
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse({"ok": False, "error": "به این بخش دسترسی ندارید.",
                             "panel_url": reverse("panel_home")}, status=403)
    if request.method == "GET" and request.path in {"/studio/", "/sales/", "/team/", "/procurement/"}:
        messages.info(request, "دسترسی این فضای کاری تغییر کرده است؛ از پنل زاد وارد شوید.")
        return redirect("panel_home")
    return render(request, "main/pages/panel/forbidden.html", status=403)
