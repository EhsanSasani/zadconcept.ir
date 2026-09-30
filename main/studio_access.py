"""Shared permissions for the independent Studio and florist workspaces."""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache

from .models import Florist


def wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


def can_manage_studio(user):
    return bool(user.is_authenticated and user.is_active and user.has_perm("main.view_studioproduct"))


def require_studio_permission(request, permission="view_studioproduct"):
    if not (request.user.is_authenticated and request.user.is_active
            and request.user.has_perm(f"main.{permission}")):
        raise PermissionDenied


def get_active_florist(user):
    if not (user.is_authenticated and user.is_active):
        return None
    return Florist.objects.filter(user_id=user.pk, is_active=True).first()


def team_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if wants_json(request):
                return JsonResponse({"ok": False, "errors": {"__all__": [
                    "نشست شما پایان یافته؛ دوباره وارد شوید. پیش‌نویس را نگه دارید."]},
                    "login_url": reverse("studio_login")}, status=401)
            return redirect_to_login(request.get_full_path(), reverse("studio_login"))
        florist = get_active_florist(request.user)
        if florist is None:
            if wants_json(request):
                return JsonResponse({"ok": False, "errors": {"__all__": [
                    "دسترسی پنل فلوریست برای این حساب فعال نیست؛ با مدیر استودیو تماس بگیرید."]}}, status=403)
            raise PermissionDenied("دسترسی پنل فلوریست برای این حساب فعال نیست.")
        request.florist = florist
        return view(request, *args, **kwargs)
    return never_cache(wrapped)


def portal_context(request, active):
    return {"active": active, "florist": getattr(request, "florist", None),
            "can_manage_studio": can_manage_studio(request.user)}
