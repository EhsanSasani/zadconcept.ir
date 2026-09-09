"""Permission-aware presentation for the existing Django admin."""
from django import template
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.urls import reverse

register = template.Library()

GROUPS = (
    ("products", "محصولات", "fa-box-open", ("flower", "samedayflower", "weddingproduct", "bakeryitem", "giftitem", "category", "tag")),
    ("pages", "صفحات سایت", "fa-file-alt", ("sitehero", "weddingpagecontent", "weddingfilm", "weddingcollectioncontent", "workshoppagecontent", "pagecontentblock", "newspost", "event", "workshopgalleryimage")),
    ("stories", "استوری‌ها", "fa-play-circle", ("story", "storyclip")),
    ("requests", "درخواست‌ها", "fa-comment-dots", ("leadrequest",)),
    ("settings", "تنظیمات و دسترسی‌ها", "fa-sliders-h", ("telegrambotuser", "herofont", "user", "group")),
    ("archive", "تنظیمات قدیمی", "fa-archive", ("homeheroslide",)),
)


def _navigation(request):
    if hasattr(request, "_zad_admin_navigation"):
        return request._zad_admin_navigation
    apps = admin.site.get_app_list(request)
    models = {m["object_name"].lower(): m for app in apps for m in app["models"]}
    groups, used = [], set()
    for key, label, icon, names in GROUPS:
        items = []
        for name in names:
            model = models.get(name)
            if not model:
                continue
            used.add(name)
            item = dict(model)
            item["active"] = bool(model.get("admin_url") and request.path.startswith(model["admin_url"]))
            items.append(item)
        if items:
            groups.append({"key": key, "label": label, "icon": icon, "items": items, "active": any(i["active"] for i in items)})
    rest = [m for name, m in models.items() if name not in used]
    if rest:
        groups.append({"key": "other", "label": "سایر امکانات", "icon": "fa-ellipsis-h", "items": rest})
    request._zad_admin_navigation = groups
    return groups


@register.inclusion_tag("admin/zad/sidebar.html", takes_context=True)
def zad_admin_sidebar(context):
    request = context["request"]
    return {"groups": _navigation(request), "request": request, "user": request.user}


@register.simple_tag(takes_context=True)
def zad_dashboard(context):
    request = context["request"]
    groups = _navigation(request)
    links = {item["object_name"].lower(): item for group in groups for item in group["items"]}
    specs = (
        ("خانه", "index", "story", "main/img/home/moments/flowers-640.webp", "استوری‌ها و ارسال روز؛ تصاویر اصلی فعلاً ثابت‌اند"),
        ("استودیو گل", "flowers", "flower", "main/img/home/moments/flowers-640.webp", "محصولات، دسته‌بندی‌ها و کاورها"),
        ("عروسی", "weddings", "weddingpagecontent", "main/img/home/moments/wedding-640.webp", "متن، تصاویر و گالری صفحه"),
        ("ورکشاپ‌ها", "events", "workshoppagecontent", "main/img/home/moments/workshops-640.webp", "متن برنامه‌های پیش رو"),
    )
    pages = []
    for title, route, model, artwork, note in specs:
        link = links.get(model)
        if link and link.get("admin_url"):
            pages.append({"title": title, "url": link["admin_url"], "public_url": reverse(route), "image": artwork, "note": note})
    actions = []
    for model, label in (("flower", "افزودن محصول"), ("story", "استوری جدید"), ("leadrequest", "درخواست‌ها")):
        item = links.get(model)
        if item:
            url = item.get("admin_url") if model == "leadrequest" else item.get("add_url")
            if url:
                actions.append({"label": label, "url": url})
    allowed = {item["model"]._meta.concrete_model._meta.model_name for group in groups for item in group["items"]}
    # Only show this user's own activity, limited to models still accessible.
    history = list(LogEntry.objects.filter(user=request.user, content_type__model__in=allowed).select_related("content_type").order_by("-action_time")[:6])
    return {"groups": groups, "pages": pages, "actions": actions, "history": history}


@register.simple_tag(takes_context=True)
def zad_connection(context):
    from main.admin_content import connection_guidance
    opts = context.get("opts")
    if not opts or opts.app_label != "main":
        return None
    obj = context.get("original")
    guide = connection_guidance(opts.model_name, obj)
    return guide if guide.get("text") else None


@register.simple_tag(takes_context=True)
def zad_product_placement(context):
    from main.models import Product
    obj = context.get("original")
    if not isinstance(obj, Product):
        return None
    is_public = obj.is_active and obj.publish_status == Product.PublishStatus.PUBLISHED
    return {
        "name": obj.name,
        "category": obj.category.name if obj.category_id else "بدون دسته‌بندی",
        "scope": obj.get_catalog_scope_display(),
        "publication": obj.get_publish_status_display(),
        "stock": obj.get_stock_status_display(),
        "is_public": is_public,
        "url": obj.get_absolute_url() if is_public and obj.category_id else "",
    }
