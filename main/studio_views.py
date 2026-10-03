"""Private, server-rendered ZAD Studio Operations views."""
from datetime import date, datetime, time, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Case, CharField, Count, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.cache import never_cache

from .image_pipeline import ImageUploadError, normalize_admin_image
from .studio_access import require_studio_permission
from .studio_admin_notifications import admin_notifications_enabled
from .models import Florist, StudioDelivery, StudioIngestionIssue, StudioProduct, TelegramSameDayPost


def _access(request, permission="view_studioproduct"):
    require_studio_permission(request, permission)


def _period(request):
    today = timezone.localdate()
    choice = request.GET.get("period", "30")
    if choice == "today":
        start, end = today, today
    elif choice == "7":
        start, end = today - timedelta(days=6), today
    elif choice == "90":
        start, end = today - timedelta(days=89), today
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


def _activity(period, *, florist=None, production_type=None, include_deleted=False):
    qs = StudioProduct.objects.select_related("florist", "product").filter(
        _event_filter("produced_at", period) | _event_filter("sold_at", period)
        | _event_filter("withdrawn_at", period))
    if not include_deleted:
        qs = qs.exclude(status=StudioProduct.Status.DELETED)
    if florist:
        qs = qs.filter(florist=florist)
    if production_type in StudioProduct.ProductionType.values:
        qs = qs.filter(production_type=production_type)
    return qs


def _event_filter(field, period):
    return Q(**{field + "__gte": period["lower"], field + "__lt": period["upper"]})


def _stats(qs, period):
    produced = _event_filter("produced_at", period)
    sold = Q(status=StudioProduct.Status.SOLD) & _event_filter("sold_at", period)
    withdrawn = Q(status=StudioProduct.Status.WITHDRAWN) & _event_filter("withdrawn_at", period)
    values = qs.aggregate(
        produced=Count("pk", filter=produced), sold=Count("pk", filter=sold),
        withdrawn=Count("pk", filter=withdrawn),
        available=Count("pk", filter=produced & Q(status=StudioProduct.Status.AVAILABLE)),
        cancelled=Count("pk", filter=produced & Q(status=StudioProduct.Status.CANCELLED)),
        cohort_sold=Count("pk", filter=produced & Q(status=StudioProduct.Status.SOLD)),
        total_value=Sum("price", filter=produced),
        sold_value=Sum("price", filter=sold), average_price=Avg("price", filter=produced),
        average_time=Avg(F("sold_at") - F("produced_at"), filter=sold),
    )
    # Conversion remains a cohort metric: sales of older stock must not make
    # this period's production conversion exceed 100%.
    values["sell_through"] = round(100 * values["cohort_sold"] / values["produced"]) if values["produced"] else 0
    values["outcome_total"] = sum(values[key] for key in ("sold", "withdrawn", "available", "cancelled"))
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


def _sort_state(request, allowed, default, prefix=""):
    key = request.GET.get(prefix + "sort", default)
    if key not in allowed:
        key = default
    direction = request.GET.get(prefix + "dir", "desc" if key == default else "asc")
    if direction not in {"asc", "desc"}:
        direction = "desc" if key == default else "asc"
    return {"key": key, "direction": direction, "prefix": prefix}


def _choice_order(field, choices):
    return Case(*[When(**{field: key}, then=Value(label)) for key, label in choices],
                default=Value(""), output_field=CharField())


def _sort_products(request, qs):
    fields = {"product": "type_label", "factor": "factor_code", "florist": "florist__name",
              "production": "production_label", "price": "price", "status": "status_label",
              "produced": "produced_at", "result": "result_at"}
    state = _sort_state(request, fields, "produced")
    qs = qs.annotate(type_label=_choice_order("product_type", StudioProduct.ProductType.choices),
                     production_label=_choice_order("production_type", StudioProduct.ProductionType.choices),
                     status_label=_choice_order("status", StudioProduct.Status.choices),
                     result_at=Coalesce("sold_at", "withdrawn_at"))
    expression = F(fields[state["key"]])
    order = expression.desc(nulls_last=True) if state["direction"] == "desc" else expression.asc(nulls_last=True)
    return qs.order_by(order, "pk"), state


def _chart(qs, period):
    series = {}
    for key, field, status in (("produced", "produced_at", None),
                               ("sold", "sold_at", StudioProduct.Status.SOLD),
                               ("withdrawn", "withdrawn_at", StudioProduct.Status.WITHDRAWN)):
        rows = qs.filter(_event_filter(field, period))
        if status:
            rows = rows.filter(status=status)
        series[key] = {row["day"].isoformat(): row["count"] for row in rows.annotate(
            day=TruncDate(field, tzinfo=timezone.get_current_timezone())
        ).values("day").annotate(count=Count("pk"))}
    days = min((period["end"] - period["start"]).days + 1, 31)
    start = period["end"] - timedelta(days=days - 1)
    return [{"label": (start + timedelta(days=i)).isoformat(),
             **{key: values.get((start + timedelta(days=i)).isoformat(), 0)
                for key, values in series.items()}} for i in range(days)]


def _base(request, active, period=None):
    keep = {"q", "florist", "production_type", "status", "product_type", "source", "sort", "dir"}
    return {"active": active, "period": period,
            "private_notifications_enabled": admin_notifications_enabled(),
            "period_filters": [(key, value) for key, value in request.GET.items() if key in keep], "nav": [
        ("dashboard", "داشبورد", "studio_dashboard"),
        ("products", "محصولات", "studio_products"),
        ("florists", "فلوریست‌ها", "studio_florists"),
        ("analytics", "تحلیل‌ها", "studio_analytics"),
        ("add", "ثبت محصول", "studio_product_add"),
        ("settings", "تنظیمات", "studio_settings"),
    ]}


@never_cache
@login_required(login_url="studio_login")
def dashboard(request):
    _access(request)
    period = _period(request)
    qs = _activity(period)
    stats = _stats(qs, period)
    previous = _stats(_activity(_previous(period)), _previous(period))
    comparisons = {key: _delta(stats[key], previous[key]) for key in
                   ("produced", "sold", "withdrawn", "available", "total_value")}
    breakdown = dict(qs.filter(_event_filter("produced_at", period)).values_list("production_type").annotate(count=Count("pk")))
    daily = breakdown.get(StudioProduct.ProductionType.DAILY, 0)
    custom = breakdown.get(StudioProduct.ProductionType.CUSTOM, 0)
    chart = _chart(qs, period)
    latest, table_sort = _sort_products(request, qs)
    florist_rows = []
    for florist in Florist.objects.filter(is_active=True):
        florist_rows.append({"florist": florist, "stats": _stats(qs.filter(florist=florist), period)})
    missing_count = TelegramSameDayPost.objects.filter(product__isnull=False, product__studio_record__isnull=True).count()
    issue_count = StudioIngestionIssue.objects.filter(resolved_at__isnull=True).count()
    context = {**_base(request, "dashboard", period), "stats": stats, "comparisons": comparisons,
               "daily": daily, "custom": custom, "chart": chart, "florists": florist_rows,
               "latest": latest[:5], "table_sort": table_sort,
               "missing_count": missing_count, "issue_count": issue_count}
    return render(request, "main/studio/dashboard.html", context)


@never_cache
@login_required(login_url="studio_login")
def products(request):
    _access(request)
    period = _period(request)
    qs = _activity(period, include_deleted=True)
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
    summary = _stats(qs.exclude(status=StudioProduct.Status.DELETED), period)
    qs, table_sort = _sort_products(request, qs)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "main/studio/products.html", {
        **_base(request, "products", period), "page": page, "summary": summary, "table_sort": table_sort,
        "florists": Florist.objects.all(),
        "status_choices": StudioProduct.Status.choices, "type_choices": StudioProduct.ProductType.choices,
        "production_choices": StudioProduct.ProductionType.choices, "source_choices": StudioProduct.Source.choices})


@never_cache
@login_required(login_url="studio_login")
def florists(request):
    _access(request)
    period = _period(request)
    rows = [{"florist": florist, "stats": _stats(_activity(period, florist=florist), period)}
            for florist in Florist.objects.all()]
    return render(request, "main/studio/florists.html", {
        **_base(request, "florists", period), "rows": rows})


@never_cache
@login_required(login_url="studio_login")
def florist_profile(request, pk):
    _access(request)
    florist = get_object_or_404(Florist, pk=pk)
    period = _period(request)
    production_type = request.GET.get("production_type")
    qs = _activity(period, florist=florist, production_type=production_type)
    breakdown = list(qs.filter(_event_filter("produced_at", period)).values("product_type").annotate(count=Count("pk")).order_by("-count"))
    split = dict(qs.filter(_event_filter("produced_at", period)).values_list("production_type").annotate(count=Count("pk")))
    chart = _chart(qs, period)
    qs, table_sort = _sort_products(request, qs)
    return render(request, "main/studio/profile.html", {
        **_base(request, "florists", period), "florist": florist, "stats": _stats(qs, period),
        "chart": chart, "table_sort": table_sort,
        "breakdown": breakdown, "daily": split.get("DAILY", 0), "custom": split.get("CUSTOM", 0),
        "page": Paginator(qs, 15).get_page(request.GET.get("page"))})


@never_cache
@login_required(login_url="studio_login")
def analytics(request):
    _access(request)
    period = _period(request)
    qs = _activity(period)
    produced = _event_filter("produced_at", period)
    sold = Q(status="SOLD") & _event_filter("sold_at", period)
    withdrawn = Q(status="WITHDRAWN") & _event_filter("withdrawn_at", period)
    by_type = list(qs.values("product_type").annotate(
        produced=Count("pk", filter=produced), sold=Count("pk", filter=sold),
        withdrawn=Count("pk", filter=withdrawn),
        cohort_sold=Count("pk", filter=produced & Q(status="SOLD")),
        sold_value=Sum("price", filter=sold)).order_by("-produced"))
    for row in by_type:
        row["sell_through"] = round(row["cohort_sold"] / row["produced"] * 100) if row["produced"] else 0
    fields = {"type": "product_type", "produced": "produced", "sold": "sold", "withdrawn": "withdrawn",
              "rate": "sell_through", "value": "sold_value"}
    table_sort = _sort_state(request, fields, "produced")
    labels = dict(StudioProduct.ProductType.choices)
    by_type.sort(key=lambda row: labels[row["product_type"]] if table_sort["key"] == "type"
                 else (row[fields[table_sort["key"]]] or 0), reverse=table_sort["direction"] == "desc")
    split = dict(qs.filter(_event_filter("produced_at", period)).values_list("production_type").annotate(count=Count("pk")))
    return render(request, "main/studio/analytics.html", {
        **_base(request, "analytics", period), "stats": _stats(qs, period), "by_type": by_type, "table_sort": table_sort,
        "daily": split.get("DAILY", 0), "custom": split.get("CUSTOM", 0)})


class FloristForm(forms.ModelForm):
    photo = forms.FileField(label="عکس پروفایل", required=False,
                            help_text="اختیاری · JPG، PNG، WebP یا HEIC؛ حداکثر ۲۰ مگابایت",
                            widget=forms.ClearableFileInput(attrs={"accept": "image/*,.heic,.heif"}))

    def clean_photo(self):
        try:
            return normalize_admin_image(self.cleaned_data.get("photo"), max_dimension=800)
        except ImageUploadError as error:
            raise forms.ValidationError(str(error)) from error

    class Meta:
        model = Florist
        fields = ("photo", "name", "code", "is_active", "joined_at", "left_at", "notes")
        widgets = {"joined_at": forms.DateInput(attrs={"type": "date"}),
                   "left_at": forms.DateInput(attrs={"type": "date"})}


@never_cache
@login_required(login_url="studio_login")
@require_http_methods(["GET", "POST"])
def florist_add(request):
    _access(request, "add_florist")
    form = FloristForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        florist = form.save()
        messages.success(request, "فلوریست ثبت شد.")
        return redirect("studio_florist_profile", pk=florist.pk)
    return render(request, "main/studio/form.html", {
        **_base(request, "florists"), "form": form, "title": "افزودن فلوریست", "submit_label": "ثبت فلوریست", "is_florist_form": True})


@never_cache
@login_required(login_url="studio_login")
@require_http_methods(["GET", "POST"])
def florist_edit(request, pk):
    _access(request, "change_florist")
    florist = get_object_or_404(Florist, pk=pk)
    form = FloristForm(request.POST or None, request.FILES or None, instance=florist)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "اطلاعات فلوریست به‌روزرسانی شد.")
        return redirect("studio_florist_profile", pk=florist.pk)
    return render(request, "main/studio/form.html", {
        **_base(request, "florists"), "form": form, "title": "ویرایش فلوریست", "submit_label": "ذخیره تغییرات", "is_florist_form": True,
        "preview_url": florist.photo.url if florist.photo else ""})


class ProductForm(forms.ModelForm):
    image = forms.FileField(label="تصویر محصول", required=True,
                            widget=forms.ClearableFileInput(attrs={"accept": "image/*,.heic,.heif,.avif"}))

    class Meta:
        model = StudioProduct
        fields = ("image", "florist", "factor_code", "product_type", "production_type", "price", "status", "notes")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["florist"].queryset = Florist.objects.filter(is_active=True)
        self.fields["florist"].label = "فلوریست سازنده"
        self.fields["florist"].empty_label = "فلوریست را انتخاب کنید"
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
        # An existing maker remains selectable after leaving the team; editing
        # the price must not require reassigning their historical production.
        self.fields["florist"].queryset = Florist.objects.filter(
            Q(is_active=True) | Q(pk=self.instance.florist_id))

    def clean_production_type(self):
        value = self.cleaned_data["production_type"]
        if value != self.instance.production_type:
            raise forms.ValidationError("نوع تولید پس از ثبت قابل تغییر نیست؛ برای اصلاح با مدیر هماهنگ کنید.")
        return value

    def clean_image(self):
        if self.cleaned_data.get("image") is False:
            raise forms.ValidationError("تصویر محصول لازم است؛ برای تغییر، عکس جایگزین انتخاب کنید.")
        return super().clean_image()

    def clean_factor_code(self):
        value = super().clean_factor_code()
        if (value != self.instance.factor_code
                and self.instance.deliveries.filter(action=StudioDelivery.Action.PUBLISH).exists()):
            raise forms.ValidationError("شماره فاکتور محصول دارای ارسال تلگرام قابل تغییر نیست.")
        return value


@never_cache
@login_required(login_url="studio_login")
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
        from .studio_publishing import save_dashboard_record
        try:
            save_dashboard_record(record)
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            if (record.production_type == StudioProduct.ProductionType.DAILY
                    and record.status == StudioProduct.Status.AVAILABLE):
                messages.success(request, "محصول ثبت شد و در صف انتشار سایت و گروه آماده‌ها قرار گرفت.")
            else:
                messages.success(request, "محصول در دفتر تولید ثبت شد.")
            return redirect("studio_products")
    return render(request, "main/studio/form.html", {
        **_base(request, "add"), "form": form, "title": "ثبت محصول", "submit_label": "ثبت محصول",
        "help_text": "محصول روزانهٔ موجود در سایت و گروه آماده‌ها منتشر می‌شود؛ محصول سفارشی فقط در دفتر تولید می‌ماند."})


@never_cache
@login_required(login_url="studio_login")
@require_http_methods(["GET", "POST"])
def product_edit(request, pk):
    _access(request, "change_studioproduct")
    record = get_object_or_404(StudioProduct, pk=pk)
    if record.source not in {StudioProduct.Source.DASHBOARD, StudioProduct.Source.ADMIN} or record.status != StudioProduct.Status.AVAILABLE:
        raise PermissionDenied
    form = ProductEditForm(request.POST or None, request.FILES or None, instance=record)
    if request.method == "POST" and form.is_valid():
        from .studio_publishing import update_dashboard_record
        try:
            record = update_dashboard_record(form.save(commit=False), changed_fields=form.changed_data)
        except ValidationError as error:
            if hasattr(error, "message_dict"):
                for field, errors in error.message_dict.items():
                    form.add_error(field if field in form.fields else None, errors)
            else:
                form.add_error(None, error)
        else:
            messages.success(request, "اطلاعات محصول اصلاح شد.")
            return redirect("studio_products")
    return render(request, "main/studio/form.html", {
        **_base(request, "products"), "form": form, "title": f"ویرایش فاکتور {record.factor_code}",
        "submit_label": "ذخیره تغییرات", "preview_url": record.photo_url,
        "help_text": "این فرم فقط رکوردهای دستیِ موجود را اصلاح می‌کند."})


@never_cache
@login_required(login_url="studio_login")
@require_POST
def product_status(request, pk):
    _access(request, "change_studioproduct")
    record = get_object_or_404(StudioProduct, pk=pk)
    if record.deliveries.filter(action=StudioDelivery.Action.PUBLISH).exists():
        from .studio_delivery import set_portal_status
        try:
            set_portal_status(record, request.POST.get("status"), actor=request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "وضعیت محصول ثبت شد و رسیدگی به پیام گروه پیگیری می‌شود.")
        return redirect("studio_products")
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


@never_cache
@login_required(login_url="studio_login")
@require_POST
def product_delete(request, pk):
    _access(request, "delete_studioproduct")
    record = get_object_or_404(StudioProduct, pk=pk)
    from .studio_delivery import soft_delete_product
    try:
        soft_delete_product(
            record,
            actor=request.user,
            reason=request.POST.get("reason", ""),
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "محصول از عملکرد فلوریست حذف شد؛ سابقهٔ مدیریتی آن محفوظ است.")
    return redirect("studio_products")


@never_cache
@login_required(login_url="studio_login")
def settings_view(request):
    _access(request)
    from django.conf import settings
    missing_qs = TelegramSameDayPost.objects.filter(
        product__isnull=False, product__studio_record__isnull=True,
    ).select_related("product").order_by("-telegram_created_at")
    missing = missing_qs.count()
    issues = StudioIngestionIssue.objects.filter(resolved_at__isnull=True).order_by("-updated_at")
    issue_fields = {"message": "telegram_message_id", "reason": "reason", "date": "updated_at"}
    issue_sort = _sort_state(request, issue_fields, "date", "issues_")
    issues = issues.order_by(("-" if issue_sort["direction"] == "desc" else "") + issue_fields[issue_sort["key"]], "pk")
    missing_fields = {"product": "product__name", "message": "telegram_message_id", "date": "telegram_created_at", "error": "studio_error"}
    missing_sort = _sort_state(request, missing_fields, "date", "missing_")
    missing_qs = missing_qs.order_by(("-" if missing_sort["direction"] == "desc" else "") + missing_fields[missing_sort["key"]], "pk")
    return render(request, "main/studio/settings.html", {
        **_base(request, "settings"), "missing_count": missing,
        "issue_sort": issue_sort, "missing_sort": missing_sort,
        "missing_posts": missing_qs[:50],
        "issue_count": issues.count(), "issues": issues[:50],
        "daily_strict": settings.STUDIO_DAILY_REQUIRE_METADATA,
        "custom_connected": bool(settings.TELEGRAM_STUDIO_CUSTOM_GROUP_ID),
        "delivery_waiting": StudioDelivery.objects.exclude(status=StudioDelivery.Status.SENT).count(),
        "daily_connected": bool(settings.TELEGRAM_SAME_DAY_GROUP_ID and settings.TELEGRAM_SAME_DAY_CATEGORY_ID)})


@never_cache
@login_required(login_url="studio_login")
@require_http_methods(["GET", "POST"])
def deliveries(request):
    """A separate operations view keeps the everyday dashboard uncluttered."""
    _access(request)
    if request.method == "POST":
        _access(request, "change_studioproduct")
        from .studio_delivery import reconcile_delivery, retry_delivery, retry_uncertain_delivery
        pk = request.POST.get("delivery_id", "")
        if not pk.isdecimal():
            raise PermissionDenied
        delivery = get_object_or_404(StudioDelivery, pk=int(pk))
        try:
            if request.POST.get("action") == "retry":
                retry_delivery(delivery.pk)
                messages.success(request, "درخواست برای تلاش مجدد در صف قرار گرفت.")
            elif request.POST.get("action") == "reconcile":
                message_id = request.POST.get("message_id", "").strip()
                if not message_id.isdecimal() or int(message_id) <= 0 or request.POST.get("verified") != "yes":
                    raise ValidationError("پیام همین محصول را در گروه آماده‌ها بررسی کنید و شناسهٔ عددی آن را وارد کنید.")
                reconcile_delivery(delivery.pk, int(message_id))
                messages.success(request, "پیام تأییدشده به محصول متصل شد؛ پیام تازه‌ای ارسال نشد.")
            elif request.POST.get("action") == "retry_absent":
                retry_uncertain_delivery(delivery.pk, actor=request.user,
                    confirmed_absent=request.POST.get("verified_absent") == "yes")
                messages.success(request, "با تأیید شما، ارسال دوباره در صف قرار گرفت.")
            else:
                raise PermissionDenied
        except (ValidationError, ValueError) as error:
            detail = " ".join(error.messages) if isinstance(error, ValidationError) else "این اقدام برای وضعیت فعلی مجاز نیست."
            messages.error(request, detail)
        return redirect("studio_deliveries")

    qs = StudioDelivery.objects.select_related("record", "record__florist")
    counts = dict(qs.values_list("status").annotate(total=Count("pk")))
    state = request.GET.get("status", "")
    if state in StudioDelivery.Status.values:
        qs = qs.filter(status=state)
    q = request.GET.get("q", "").strip()[:40]
    if q:
        qs = qs.filter(record__factor_code__icontains=q)
    fields = {"factor": "record__factor_code", "action": "action", "status": "status", "attempts": "attempts", "date": "created_at"}
    table_sort = _sort_state(request, fields, "date")
    qs = qs.order_by(("-" if table_sort["direction"] == "desc" else "") + fields[table_sort["key"]], "-pk")
    return render(request, "main/studio/deliveries.html", {
        **_base(request, "settings"), "page": Paginator(qs, 20).get_page(request.GET.get("page")),
        "status_choices": StudioDelivery.Status.choices, "table_sort": table_sort,
        "waiting": sum(counts.get(key, 0) for key in ("PENDING", "SENDING", "RETRY")),
        "needs_review": sum(counts.get(key, 0) for key in ("UNCERTAIN", "FAILED")),
        "delivered": counts.get("SENT", 0),
    })


@never_cache
@login_required(login_url="studio_login")
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
