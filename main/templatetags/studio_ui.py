from django import template

register = template.Library()
DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


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
