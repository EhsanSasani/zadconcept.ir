"""Private, server-rendered ZAD Studio Operations views."""
from datetime import date, datetime, time, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .image_pipeline import ImageUploadError, normalize_admin_image
from .models import Florist, StudioIngestionIssue, StudioProduct, TelegramSameDayPost


def _access(request, permission="view_studioproduct"):
    if not request.user.is_staff or not request.user.has_perm(f"main.{permission}"):
        raise PermissionDenied


def _period(request):
    today = timezone.localdate()
    choice = request.GET.get("period", "30")
    if choice == "today":
        start, end = today, today
    elif choice == "7":
        start, end = today - timedelta(days=6), today
    elif choice == "month":
        start, end = today.replace(day=1), today
    elif choice == "custom":
        try:
            start = date.fromisoformat(request.GET["start"])
            end = date.fromisoformat(request.GET["end"])
            if start > end or (end - start).days > 366 or end > today:
                raise ValueError
        except (KeyError, ValueError):
            start, end, choice = today - timedelta(days=29), today, "30"
    else:
        start, end, choice = today - timedelta(days=29), today, "30"
    tz = timezone.get_current_timezone()
    lower = timezone.make_aware(datetime.combine(start, time.min), tz)
    upper = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)
    return {"choice": choice, "start": start, "end": end, "lower": lower, "upper": upper}


def _cohort(period, *, florist=None, production_type=None):
    qs = StudioProduct.objects.select_related("florist", "product").filter(
        produced_at__gte=period["lower"], produced_at__lt=period["upper"])
    if florist:
        qs = qs.filter(florist=florist)
    if production_type in StudioProduct.ProductionType.values:
        qs = qs.filter(production_type=production_type)
    return qs


def _stats(qs):
    values = qs.aggregate(
        produced=Count("pk"), sold=Count("pk", filter=Q(status=StudioProduct.Status.SOLD)),
        withdrawn=Count("pk", filter=Q(status=StudioProduct.Status.WITHDRAWN)),
        available=Count("pk", filter=Q(status=StudioProduct.Status.AVAILABLE)),
        cancelled=Count("pk", filter=Q(status=StudioProduct.Status.CANCELLED)),
        total_value=Sum("price"),
        sold_value=Sum("price", filter=Q(status=StudioProduct.Status.SOLD)),
        average_price=Avg("price"),
        average_time=Avg(F("sold_at") - F("produced_at"), filter=Q(status=StudioProduct.Status.SOLD)),
    )
    values["sell_through"] = round(100 * values["sold"] / values["produced"]) if values["produced"] else 0
    duration = values["average_time"]
    values["average_days"] = round(duration.total_seconds() / 86400, 1) if duration else None
    for key in ("total_value", "sold_value", "average_price"):
        values[key] = values[key] or 0
    return values


def _previous(period):
    days = (period["end"] - period["start"]).days + 1
    return {"lower": period["lower"] - timedelta(days=days), "upper": period["lower"]}


def _delta(current, previous):
    if previous is None or previous == 0:
        return None
    return round((current - previous) * 100 / previous)


def _base(request, active, period=None):
    return {"active": active, "period": period, "nav": [
        ("dashboard", "داشبورد", "studio_dashboard"),
        ("products", "محصولات", "studio_products"),
        ("florists", "فلوریست‌ها", "studio_florists"),
        ("analytics", "تحلیل‌ها", "studio_analytics"),
        ("add", "ثبت محصول", "studio_product_add"),
        ("settings", "تنظیمات", "studio_settings"),
    ]}


@login_required(login_url="/admin/login/")
def dashboard(request):
    _access(request)
    period = _period(request)
    qs = _cohort(period)
    stats = _stats(qs)
    previous = _stats(_cohort(_previous(period)))
    comparisons = {key: _delta(stats[key], previous[key]) for key in
                   ("produced", "sold", "withdrawn", "available", "total_value")}
    breakdown = dict(qs.values_list("production_type").annotate(count=Count("pk")))
    daily = breakdown.get(StudioProduct.ProductionType.DAILY, 0)
    custom = breakdown.get(StudioProduct.ProductionType.CUSTOM, 0)
    trend = {row["day"].isoformat(): row for row in qs.annotate(
        day=TruncDate("produced_at", tzinfo=timezone.get_current_timezone())
    ).values("day").annotate(produced=Count("pk"), sold=Count("pk", filter=Q(status="SOLD")))}
    days = min((period["end"] - period["start"]).days + 1, 31)
    offset = (period["end"] - period["start"]).days + 1 - days
    chart = [{"label": (period["start"] + timedelta(days=offset + i)).isoformat(),
              "produced": trend.get((period["start"] + timedelta(days=offset + i)).isoformat(), {}).get("produced", 0),
              "sold": trend.get((period["start"] + timedelta(days=offset + i)).isoformat(), {}).get("sold", 0)}
             for i in range(days)]
    florist_rows = []
    for florist in Florist.objects.filter(is_active=True):
        florist_rows.append({"florist": florist, "stats": _stats(qs.filter(florist=florist))})
    missing_count = TelegramSameDayPost.objects.filter(product__isnull=False, product__studio_record__isnull=True).count()
    issue_count = StudioIngestionIssue.objects.filter(resolved_at__isnull=True).count()
    context = {**_base(request, "dashboard", period), "stats": stats, "comparisons": comparisons,
               "daily": daily, "custom": custom, "chart": chart, "florists": florist_rows,
               "latest": StudioProduct.objects.select_related("florist", "product")[:5],
               "missing_count": missing_count, "issue_count": issue_count}
    return render(request, "main/studio/dashboard.html", context)


@login_required(login_url="/admin/login/")
def products(request):
    _access(request)
    period = _period(request)
    qs = _cohort(period)
    q = request.GET.get("q", "").strip()[:80]
    if q:
        matching_types = [key for key, label in StudioProduct.ProductType.choices
                          if q in label or q.casefold() in key.casefold()]
        qs = qs.filter(Q(factor_code__icontains=q) | Q(florist__name__icontains=q) |
                       Q(florist__code__icontains=q) | Q(product__name__icontains=q) |
                       Q(product_type__in=matching_types))
    for field in ("status", "production_type", "product_type", "source"):
        value = request.GET.get(field, "")
        choices = dict(StudioProduct._meta.get_field(field).choices)
        if value in choices:
            qs = qs.filter(**{field: value})
    florist_id = request.GET.get("florist", "")
    if florist_id.isdecimal():
        qs = qs.filter(florist_id=int(florist_id))
    summary = _stats(qs)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "main/studio/products.html", {
        **_base(request, "products", period), "page": page, "summary": summary,
        "florists": Florist.objects.all(),
        "status_choices": StudioProduct.Status.choices, "type_choices": StudioProduct.ProductType.choices,
        "production_choices": StudioProduct.ProductionType.choices, "source_choices": StudioProduct.Source.choices})


@login_required(login_url="/admin/login/")
def florists(request):
    _access(request)
    period = _period(request)
    rows = [{"florist": florist, "stats": _stats(_cohort(period, florist=florist))}
            for florist in Florist.objects.all()]
    return render(request, "main/studio/florists.html", {
        **_base(request, "florists", period), "rows": rows})


@login_required(login_url="/admin/login/")
def florist_profile(request, pk):
    _access(request)
    florist = get_object_or_404(Florist, pk=pk)
    period = _period(request)
    production_type = request.GET.get("production_type")
    qs = _cohort(period, florist=florist, production_type=production_type)
    breakdown = list(qs.values("product_type").annotate(count=Count("pk")).order_by("-count"))
    split = dict(qs.values_list("production_type").annotate(count=Count("pk")))
    return render(request, "main/studio/profile.html", {
        **_base(request, "florists", period), "florist": florist, "stats": _stats(qs),
        "breakdown": breakdown, "daily": split.get("DAILY", 0), "custom": split.get("CUSTOM", 0),
        "page": Paginator(qs, 15).get_page(request.GET.get("page"))})


@login_required(login_url="/admin/login/")
def analytics(request):
    _access(request)
    period = _period(request)
    qs = _cohort(period)
    by_type = list(qs.values("product_type").annotate(
        produced=Count("pk"), sold=Count("pk", filter=Q(status="SOLD")),
        withdrawn=Count("pk", filter=Q(status="WITHDRAWN")),
        sold_value=Sum("price", filter=Q(status="SOLD"))).order_by("-produced"))
    for row in by_type:
        row["sell_through"] = round(row["sold"] / row["produced"] * 100) if row["produced"] else 0
    split = dict(qs.values_list("production_type").annotate(count=Count("pk")))
    return render(request, "main/studio/analytics.html", {
        **_base(request, "analytics", period), "stats": _stats(qs), "by_type": by_type,
        "daily": split.get("DAILY", 0), "custom": split.get("CUSTOM", 0)})


class FloristForm(forms.ModelForm):
    class Meta:
        model = Florist
        fields = ("name", "code", "is_active", "joined_at", "left_at", "notes")
        widgets = {"joined_at": forms.DateInput(attrs={"type": "date"}),
                   "left_at": forms.DateInput(attrs={"type": "date"})}


@login_required(login_url="/admin/login/")
@require_http_methods(["GET", "POST"])
def florist_add(request):
    _access(request, "add_florist")
    form = FloristForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        florist = form.save()
        messages.success(request, "فلوریست ثبت شد.")
        return redirect("studio_florist_profile", pk=florist.pk)
    return render(request, "main/studio/form.html", {
        **_base(request, "florists"), "form": form, "title": "افزودن فلوریست", "submit_label": "ثبت فلوریست"})


@login_required(login_url="/admin/login/")
@require_http_methods(["GET", "POST"])
def florist_edit(request, pk):
    _access(request, "change_florist")
    florist = get_object_or_404(Florist, pk=pk)
    form = FloristForm(request.POST or None, instance=florist)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "اطلاعات فلوریست به‌روزرسانی شد.")
        return redirect("studio_florist_profile", pk=florist.pk)
    return render(request, "main/studio/form.html", {
        **_base(request, "florists"), "form": form, "title": "ویرایش فلوریست", "submit_label": "ذخیره تغییرات"})


class ProductForm(forms.ModelForm):
    image = forms.FileField(label="تصویر محصول", required=True,
                            widget=forms.ClearableFileInput(attrs={"accept": "image/*,.heic,.heif,.avif"}))

    class Meta:
        model = StudioProduct
        fields = ("image", "florist", "factor_code", "product_type", "production_type", "price", "status", "notes")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["florist"].queryset = Florist.objects.filter(is_active=True)
        self.fields["image"].required = True

    def clean_price(self):
        value = self.cleaned_data["price"]
        if value is None or value <= 0:
            raise forms.ValidationError("قیمت باید بیشتر از صفر باشد.")
        return value

    def clean_image(self):
        image = self.cleaned_data["image"]
        if hasattr(image, "_committed") and image._committed:
            return image
        try:
            return normalize_admin_image(image)
        except ImageUploadError as error:
            raise forms.ValidationError(str(error)) from error

    def clean_factor_code(self):
        import re
        value = self.cleaned_data["factor_code"].strip().upper()
        if not re.fullmatch(r"[A-Z0-9-]{1,40}", value):
            raise forms.ValidationError("فقط حروف لاتین، عدد و خط تیره مجاز است.")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("status") == StudioProduct.Status.SOLD:
            self.instance.sold_at = timezone.now()
        elif cleaned.get("status") == StudioProduct.Status.WITHDRAWN:
            self.instance.withdrawn_at = timezone.now()
        return cleaned


class ProductEditForm(ProductForm):
    class Meta(ProductForm.Meta):
        fields = ("image", "florist", "factor_code", "product_type", "production_type", "price", "notes")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].required = False


@login_required(login_url="/admin/login/")
@require_http_methods(["GET", "POST"])
def product_add(request):
    _access(request, "add_studioproduct")
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.source = StudioProduct.Source.DASHBOARD
        record.created_by = request.user
        record.produced_at = timezone.now()
        if record.status == StudioProduct.Status.SOLD:
            record.sold_at = timezone.now()
        elif record.status == StudioProduct.Status.WITHDRAWN:
            record.withdrawn_at = timezone.now()
        elif record.status == StudioProduct.Status.CANCELLED:
            record.notes = (record.notes + "\nلغو در زمان ثبت دستی").strip()
        record.full_clean()
        record.save()
        messages.success(request, "محصول در دفتر تولید ثبت شد.")
        return redirect("studio_products")
    return render(request, "main/studio/form.html", {
        **_base(request, "add"), "form": form, "title": "ثبت محصول", "submit_label": "ثبت محصول",
        "help_text": "ثبت دستی فقط در دفتر تولید انجام می‌شود؛ محصول سفارشی در سایت منتشر نمی‌شود."})


@login_required(login_url="/admin/login/")
@require_http_methods(["GET", "POST"])
def product_edit(request, pk):
    _access(request, "change_studioproduct")
    record = get_object_or_404(StudioProduct, pk=pk)
    if record.source not in {StudioProduct.Source.DASHBOARD, StudioProduct.Source.ADMIN} or record.status != StudioProduct.Status.AVAILABLE:
        raise PermissionDenied
    form = ProductEditForm(request.POST or None, request.FILES or None, instance=record)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "اطلاعات محصول اصلاح شد.")
        return redirect("studio_products")
    return render(request, "main/studio/form.html", {
        **_base(request, "products"), "form": form, "title": f"ویرایش فاکتور {record.factor_code}",
        "submit_label": "ذخیره تغییرات", "preview_url": record.photo_url,
        "help_text": "این فرم فقط رکوردهای دستیِ موجود را اصلاح می‌کند."})


@login_required(login_url="/admin/login/")
@require_POST
def product_status(request, pk):
    _access(request, "change_studioproduct")
    with transaction.atomic():
        record = get_object_or_404(StudioProduct.objects.select_for_update(), pk=pk)
        value = request.POST.get("status")
        if record.status != StudioProduct.Status.AVAILABLE or value not in {
            StudioProduct.Status.SOLD, StudioProduct.Status.WITHDRAWN, StudioProduct.Status.CANCELLED,
        }:
            messages.error(request, "تغییر وضعیت مجاز نیست.")
        elif record.product_id:
            messages.error(request, "وضعیت محصول روزانهٔ تلگرام از همان پیام یا مدیریت کاتالوگ تغییر می‌کند.")
        else:
            record.status = value
            if value == StudioProduct.Status.SOLD:
                record.sold_at = timezone.now()
            elif value == StudioProduct.Status.WITHDRAWN:
                record.withdrawn_at = timezone.now()
            record.save(update_fields=["status", "sold_at", "withdrawn_at", "updated_at"])
            messages.success(request, "وضعیت محصول ثبت شد.")
    return redirect("studio_products")


@login_required(login_url="/admin/login/")
def settings_view(request):
    _access(request)
    from django.conf import settings
    missing_qs = TelegramSameDayPost.objects.filter(
        product__isnull=False, product__studio_record__isnull=True,
    ).select_related("product").order_by("-telegram_created_at")
    missing = missing_qs.count()
    issues = StudioIngestionIssue.objects.filter(resolved_at__isnull=True).order_by("-updated_at")
    return render(request, "main/studio/settings.html", {
        **_base(request, "settings"), "missing_count": missing,
        "missing_posts": missing_qs[:50],
        "issue_count": issues.count(), "issues": issues[:50],
        "daily_strict": settings.STUDIO_DAILY_REQUIRE_METADATA,
        "custom_connected": bool(settings.TELEGRAM_STUDIO_CUSTOM_GROUP_ID)})


@login_required(login_url="/admin/login/")
@require_POST
def resolve_issue(request, pk):
    _access(request, "change_studioingestionissue")
    issue = get_object_or_404(StudioIngestionIssue, pk=pk)
    if issue.resolved_at is None:
        issue.resolved_at = timezone.now()
        issue.resolved_by = request.user
        issue.save(update_fields=["resolved_at", "resolved_by", "updated_at"])
        messages.success(request, "خطای ثبت بررسی و بسته شد.")
    return redirect("studio_settings")
