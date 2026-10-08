"""Authenticated florist workspace and minimal account administration."""
import hashlib
import posixpath
import uuid
from urllib.parse import unquote, urlsplit

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Florist, StudioProduct
from .studio_access import (can_manage_studio, get_active_florist, portal_context,
                            require_studio_permission, team_required, wants_json)
from .studio_delivery import delivery_summary
from .studio_publishing import create_portal_record
from .team_forms import TeamLoginForm, TeamProductForm, TeamProfileForm


def _landing(user):
    from .panel import workspaces
    choices = workspaces(user)
    if len(choices) == 1:
        return choices[0]["url"]
    return reverse("panel_home") if choices else None


def _safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        path = posixpath.normpath(unquote(urlsplit(target).path))
        # Check the destination against the signed-in user's workspace access.
        if path in {reverse("studio_login").rstrip("/"), reverse("studio_logout").rstrip("/")}:
            return fallback
        if request.user.is_authenticated:
            from .studio_access import can_use_sales, can_use_procurement
            if (path == '/procurement' or path.startswith('/procurement/')) and not can_use_procurement(request.user):
                return fallback
            sales = reverse("sales_home").rstrip("/")
            if (path == sales or path.startswith(sales + "/")) and not can_use_sales(request.user):
                if path != reverse("sales_history").rstrip("/") or not can_manage_studio(request.user):
                    return fallback
            studio = reverse("studio_dashboard").rstrip("/")
            team = reverse("team_home").rstrip("/")
            if (path == studio or path.startswith(studio + "/")) and not can_manage_studio(request.user):
                return fallback
            if (path == team or path.startswith(team + "/")) and not get_active_florist(request.user):
                return fallback
        return target
    return fallback


def _login_limit_key(request):
    # A small, process-local guard with the default LocMemCache, not a replacement
    # for a reverse-proxy or shared-cache rate limit. Never trust a supplied XFF.
    identity = (request.POST.get("username", "")[:150].casefold() + "|" +
                request.META.get("REMOTE_ADDR", ""))
    return "studio-login:" + hashlib.sha256(identity.encode()).hexdigest()


@never_cache
@require_http_methods(["GET", "POST"])
def studio_login(request):
    existing = _landing(request.user) if request.user.is_authenticated else None
    if existing:
        return redirect(_safe_next(request, existing))
    form = TeamLoginForm(request, data=request.POST if request.method == "POST" else None)
    if request.method == "POST":
        key = _login_limit_key(request)
        if cache.get(key, 0) >= 10:
            form.login_throttled = True
            form.is_valid()
        elif form.is_valid():
            user = form.get_user()
            destination = _landing(user)
            if destination:
                login(request, user)
                request.session.set_expiry(60 * 60 * 24 * 30 if form.cleaned_data.get("remember") else 0)
                cache.delete(key)
                # Multiple workspaces always require an explicit choice after login.
                return redirect(destination if destination == reverse("panel_home")
                                else _safe_next(request, destination))
            form.add_error(None, "دسترسی استودیو برای این حساب فعال نیست؛ با مدیر استودیو تماس بگیرید.")
        if not cache.add(key, 1, timeout=15 * 60):
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=15 * 60)
    return render(request, "main/team/login.html", {
        "form": form, "active": "login", "next": _safe_next(request, ""),
        "can_manage_studio": False})


@never_cache
@require_POST
def studio_logout(request):
    logout(request)
    return redirect("studio_login")


def _own_products(request):
    return StudioProduct.objects.filter(florist=request.florist).exclude(
        status=StudioProduct.Status.DELETED
    ).select_related("product", "florist")


def _visible_products(request):
    return StudioProduct.objects.filter(
        Q(florist=request.florist) | Q(created_by=request.user)
    ).exclude(status=StudioProduct.Status.DELETED).exclude(
        production_type=StudioProduct.ProductionType.MISC
    ).select_related("product", "florist")


@team_required
@require_GET
def team_home(request):
    products = _own_products(request)
    summary = products.aggregate(
        total_count=Count("pk"),
        today_count=Count("pk", filter=Q(produced_at__date=timezone.localdate())),
        available_count=Count("pk", filter=Q(status=StudioProduct.Status.AVAILABLE)),
        sold_count=Count("pk", filter=Q(status=StudioProduct.Status.SOLD)))
    return render(request, "main/team/home.html", {
        **portal_context(request, "home"), "summary": summary,
        "recent_products": _visible_products(request)[:6],
        "colleague_count": Florist.objects.filter(is_active=True).exclude(pk=request.florist.pk).count()})


def _success_response(request, record, *, created):
    state = delivery_summary(record)
    published = bool(record.product_id and record.product.is_published
                     and record.status == StudioProduct.Status.AVAILABLE)
    target = reverse("team_product_detail", args=[record.pk]) + ("?created=1" if created else "")
    text = "محصول ثبت شد و در سایت قرار گرفت." if published else f"محصول در کارنامهٔ {record.florist.name} ثبت شد."
    if wants_json(request):
        return JsonResponse({"ok": True, "record_id": record.pk, "redirect_url": target,
                             "next_url": reverse("team_product_add"), "message": text,
                             "published": published, "telegram_state": state["state"]}, status=201 if created else 200)
    messages.success(request, text)
    return redirect(target)


@team_required
@require_http_methods(["GET", "POST"])
def team_product_add(request):
    if request.method == "POST":
        # Browser retries retain this UUID. Resolve a known acknowledgement before
        # validating a second copy of an upload. Attribution remains fixed after
        # creation; only the original submitter can acknowledge a retry.
        try:
            key = uuid.UUID(request.POST.get("submission_key", ""))
        except (ValueError, AttributeError, TypeError):
            key = None
        if key:
            existing = StudioProduct.objects.select_related("product", "florist").filter(submission_key=key).first()
            if existing:
                selected_florist = request.POST.get("florist")
                if (existing.created_by_id != request.user.pk
                        or (selected_florist is not None and selected_florist != str(existing.florist_id))):
                    if wants_json(request):
                        return JsonResponse({"ok": False, "errors": {"submission_key": [
                            "شناسه پیش‌نویس معتبر نیست؛ یک ثبت تازه باز کنید."]}}, status=400)
                    raise PermissionDenied
                if existing.status == StudioProduct.Status.DELETED:
                    text = "این ثبت با تصمیم مدیر حذف شده است؛ برای بررسی با مدیر استودیو تماس بگیرید."
                    if wants_json(request):
                        return JsonResponse({"ok": False, "errors": {"submission_key": [text]}}, status=409)
                    messages.error(request, text)
                    return redirect("team_products")
                return _success_response(request, existing, created=False)
    form = TeamProductForm(request.POST if request.method == "POST" else None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            record, created = create_portal_record(user=request.user, **form.cleaned_data)
        except ValidationError as error:
            if hasattr(error, "message_dict"):
                for field, errors in error.message_dict.items():
                    form.add_error(field if field in form.fields else None, errors)
            else:
                form.add_error(None, error)
        except IntegrityError:
            form.add_error(None, "ثبت هم‌زمان دیگری انجام شد؛ شماره فاکتور را بررسی و دوباره تلاش کنید.")
        else:
            return _success_response(request, record, created=created)
    if request.method == "POST" and wants_json(request):
        return JsonResponse({"ok": False, "errors": {key: list(value) for key, value in form.errors.items()}}, status=400)
    return render(request, "main/team/product_form.html", {**portal_context(request, "add"), "form": form})


@team_required
@require_GET
def team_products(request):
    products = _visible_products(request)
    status = request.GET.get("status", "")
    production = request.GET.get("production", "")
    q = request.GET.get("q", "").strip()[:80]
    status_choices = [(value, label) for value, label in StudioProduct.Status.choices
                      if value != StudioProduct.Status.DELETED]
    if status in dict(status_choices):
        products = products.filter(status=status)
    else:
        status = ""
    if production in StudioProduct.ProductionType.values:
        products = products.filter(production_type=production)
    else:
        production = ""
    if q:
        from .team_forms import latin_digits
        products = products.filter(factor_code__icontains=latin_digits(q))
    return render(request, "main/team/products.html", {
        **portal_context(request, "products"), "page_obj": Paginator(products, 18).get_page(request.GET.get("page")),
        "status_filter": status, "production_filter": production, "q": q,
        "status_choices": status_choices, "production_choices": [
            choice for choice in StudioProduct.ProductionType.choices if choice[0] != "MISC"]})


@team_required
@require_GET
def team_product_detail(request, pk):
    record = get_object_or_404(_visible_products(request), pk=pk)
    delivery = delivery_summary(record)
    return render(request, "main/team/product_detail.html", {
        **portal_context(request, "products"), "record": record, "just_created": request.GET.get("created") == "1",
        "delivery_state": delivery["state"], "delivery_label": delivery["label"],
        "published": bool(record.product_id and record.product.is_published
                          and record.status == StudioProduct.Status.AVAILABLE)})


def _peer_card(florist):
    # Whitelist the projection passed to templates: never expose a peer's model,
    # account, notes, invoice codes or financial aggregates by accident.
    return {"pk": florist.pk, "name": florist.name, "photo_url": florist.photo.url if florist.photo else "",
            "product_count": florist.product_count}


@team_required
@require_GET
def team_colleagues(request):
    colleagues = Florist.objects.filter(is_active=True).exclude(pk=request.florist.pk).annotate(
        product_count=Count("studio_products", filter=~Q(studio_products__status=StudioProduct.Status.DELETED)))
    return render(request, "main/team/colleagues.html", {
        **portal_context(request, "colleagues"), "colleagues": [_peer_card(peer) for peer in colleagues]})


@team_required
@require_GET
def team_colleague_profile(request, pk):
    peer = get_object_or_404(Florist.objects.filter(is_active=True).annotate(
        product_count=Count("studio_products", filter=~Q(studio_products__status=StudioProduct.Status.DELETED))), pk=pk)
    gallery = [{"image_url": record.photo_url, "product_type": record.get_product_type_display(),
                "production_type": record.get_production_type_display(), "produced_at": record.produced_at}
               for record in peer.studio_products.select_related("product").exclude(
                   status__in=[StudioProduct.Status.CANCELLED, StudioProduct.Status.DELETED])[:24]]
    return render(request, "main/team/colleague_profile.html", {
        **portal_context(request, "colleagues"), "colleague": _peer_card(peer), "work_gallery": gallery})


@team_required
@require_http_methods(["GET", "POST"])
def team_profile(request):
    profile_form = TeamProfileForm(instance=request.florist)
    password_form = PasswordChangeForm(request.user)
    if request.method == "POST":
        if request.POST.get("action") == "password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "رمز عبور شما تغییر کرد.")
                return redirect("team_profile")
        else:
            profile_form = TeamProfileForm(request.POST, request.FILES, instance=request.florist)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "پروفایل شما به‌روز شد.")
                return redirect("team_profile")
    return render(request, "main/team/profile.html", {
        **portal_context(request, "profile"), "profile_form": profile_form, "password_form": password_form})


@require_GET
def team_manifest(request):
    return JsonResponse({"id": "/team/", "name": "استودیو زاد", "short_name": "ZAD Studio",
                         # Include the branded /studio/login/ page in standalone navigation.
                         "lang": "fa", "dir": "rtl", "start_url": reverse("panel_home"), "scope": "/",
                         "display": "standalone", "background_color": "#f7f4f0", "theme_color": "#f7f4f0",
                         "icons": [{"src": static("main/team/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
                                   {"src": static("main/team/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
                                   {"src": static("main/team/app-icon.svg"), "sizes": "any", "type": "image/svg+xml", "purpose": "any"}]},
                        content_type="application/manifest+json")


@never_cache
@login_required(login_url="studio_login")
@require_http_methods(["GET", "POST"])
def studio_accounts(request):
    require_studio_permission(request, "manage_studio_accounts")
    if request.method == "GET":
        from .account_views import index
        return index(request)
    # Old bookmarks remain valid; stale forms must not mutate accounts without
    # the current editor's version and audit contract.
    messages.warning(request, "فرم مدیریت کاربران به‌روز شده است؛ تغییر را از فرم جدید انجام دهید.")
    return redirect("studio_accounts")
