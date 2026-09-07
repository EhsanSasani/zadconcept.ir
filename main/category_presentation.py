from django.urls import reverse

from .models import Category
from .page_presentation import _category_content


SECTION_CATEGORY_ROUTE_NAMES = {
    Category.Section.FLOWERS: "flower_subcategory",
    Category.Section.BAKERY: "bakery_subcategory",
    Category.Section.GIFTS: "gift_subcategory",
}

FLOWER_CATEGORY_FALLBACKS = {
    "hand-bouquet": "main/img/flowers/categories/hand-bouquet",
    "box": "main/img/flowers/categories/box",
    "bouquet": "main/img/flowers/categories/bouquet",
    "jarl": "main/img/flowers/categories/jarl",
    "stand": "main/img/flowers/categories/stand",
    "plants": "main/img/flowers/categories/plants",
}

def _section_category_url(category):
    route_name = SECTION_CATEGORY_ROUTE_NAMES.get(category.section)

    if route_name:
        return reverse(route_name, args=[category.slug])

    return reverse(category.section)

def _category_card(category):
    content = _category_content(category)
    has_children = category.children.filter(is_active=True).exists()
    responsive_fallback = (
        FLOWER_CATEGORY_FALLBACKS.get(category.slug)
        if category.section == Category.Section.FLOWERS and not category.cover_image
        else None
    )

    return {
        "slug": category.slug,
        "label": category.name,
        "url": _section_category_url(category),
        "image": (
            category.cover_image.url
            if category.cover_image
            else f"{responsive_fallback}-960.webp"
            if responsive_fallback
            else content["image"]
        ),
        "image_640": f"{responsive_fallback}-640.webp" if responsive_fallback else "",
        "image_960": f"{responsive_fallback}-960.webp" if responsive_fallback else "",
        "intro": category.description or content["intro"],
        "has_children": has_children,
    }
