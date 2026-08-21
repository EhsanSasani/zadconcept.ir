from django.urls import reverse

from .models import Category
from .page_presentation import _category_content


SECTION_CATEGORY_ROUTE_NAMES = {
    Category.Section.FLOWERS: "flower_subcategory",
    Category.Section.BAKERY: "bakery_subcategory",
    Category.Section.GIFTS: "gift_subcategory",
}

def _section_category_url(category):
    route_name = SECTION_CATEGORY_ROUTE_NAMES.get(category.section)

    if route_name:
        return reverse(route_name, args=[category.slug])

    return reverse(category.section)

def _category_card(category):
    content = _category_content(category)
    has_children = category.children.filter(is_active=True).exists()

    return {
        "slug": category.slug,
        "label": category.name,
        "url": _section_category_url(category),
        "image": category.cover_image.url if category.cover_image else content["image"],
        "intro": category.description or content["intro"],
        "has_children": has_children,
    }
