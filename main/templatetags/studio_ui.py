from django import template

register = template.Library()
DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


@register.filter
def jalali_date(value):
    from django.utils import timezone
    from main.persian_dates import format_persian_date
    if not value:
        return "—"
    return format_persian_date(timezone.localtime(value).date())


@register.filter
def fa_number(value):
    if value is None:
        return "—"
    try:
        return f"{value:,.0f}".translate(DIGITS)
    except (TypeError, ValueError):
        return str(value).translate(DIGITS)


@register.filter
def fa_decimal(value):
    if value is None:
        return "—"
    return str(value).translate(DIGITS)


@register.filter
def percent(part, total):
    return round(100 * part / total) if total else 0


@register.filter
def type_label(value):
    from main.models import StudioProduct
    return dict(StudioProduct.ProductType.choices).get(value, value)


@register.simple_tag(takes_context=True)
def studio_query(context, **changes):
    query = context["request"].GET.copy()
    for key, value in changes.items():
        if value is None or value == "":
            query.pop(key, None)
        else:
            query[key] = value
    return "?" + query.urlencode()


@register.inclusion_tag("main/studio/partials/sort_header.html", takes_context=True)
def sort_header(context, key, label):
    state = context.get("table_sort", {})
    active = state.get("key") == key
    current = state.get("direction", "asc")
    direction = "desc" if active and current == "asc" else "asc"
    prefix = state.get("prefix", "")
    query = context["request"].GET.copy()
    query[prefix + "sort"] = key
    query[prefix + "dir"] = direction
    query.pop("page", None)
    return {"label": label, "key": prefix + key, "prefix": prefix, "href": "?" + query.urlencode(),
            "aria_sort": ("ascending" if current == "asc" else "descending") if active else "none",
            "active": active, "current": current,
            "next_direction": "افزایشی" if direction == "asc" else "کاهشی"}
