from django.shortcuts import render
from django.urls import reverse

from ..occasion_presentation import _occasion_card
from ..category_presentation import _category_card
from ..catalog_selectors import _active_categories_for_section, _active_occasion_tags, _published_products_for_section
from ..forms import LeadRequestForm
from ..managed_heroes import _get_site_hero
from ..models import Category, FLOWER_CATEGORY_SLUGS, SAME_DAY_TAG_SLUG, Tag
from ..page_context import _default_context, _with_home
from ..page_presentation import SECTION_CONTENT, _hero_from_key
from .catalog_views import SAME_DAY_TAG_SLUGS, _section_all_url


def _featured_selection(queryset, limit=10):
    featured = list(queryset.filter(featured=True)[:limit])

    if len(featured) >= limit:
        return featured

    excluded_ids = [item.pk for item in featured]
    fallback = list(queryset.exclude(pk__in=excluded_ids)[: limit - len(featured)])

    return featured + fallback

def _flower_type_cards():
    categories = {
        category.slug: category
        for category in Category.objects.for_general_catalog().filter(
            section=Category.Section.FLOWERS,
            is_active=True,
            parent__isnull=True,
            slug__in=FLOWER_CATEGORY_SLUGS,
        ).order_by("sort_order", "name")
    }

    cards = []

    for slug in ("hand-bouquet", "box", "bouquet", "stand"):
        category = categories.get(slug)
        if category:
            cards.append(_category_card(category))


    for slug in ("jarl", "plants"):
        category = categories.get(slug)
        if category:
            cards.append(_category_card(category))

    return cards

def _flower_same_day_products(limit=12):
    return list(
        _published_products_for_section(Category.Section.FLOWERS)
        .filter(tags__slug=SAME_DAY_TAG_SLUG)
        .distinct()
        .order_by("-featured", "sort_order", "-created_at")[:limit]
    )

def _category_page(request, section):
    config = SECTION_CONTENT[section]

    products_qs = _published_products_for_section(section).prefetch_related(None)

    if section == Category.Section.FLOWERS:
        products_qs = products_qs.exclude(tags__slug__in=["condolence", "condolence", "sympathy"]).distinct()

    products_qs = products_qs.order_by(
    "-featured",
    "sort_order",
    "-created_at",
)

    featured_items = _featured_selection(products_qs, limit=10)

    breadcrumbs = _with_home([{"name": config["title"], "url": None}])

    context = _default_context(
        request,
        page_type="category",
        active_nav=config["nav"],
        meta_title=config["meta_title"],
        meta_description=config["meta_description"],
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page=section,
    )

    hero_data = _hero_from_key(section)
    db_hero = _get_site_hero(section)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)

    occasion_cards = []
    subcategory_links = []
    flower_type_cards = []
    same_day_products = []

    if section == Category.Section.FLOWERS:
        flower_type_cards = _flower_type_cards()
        same_day_products = _flower_same_day_products(limit=12)
        occasion_cards = [
            _occasion_card(tag, for_flowers=True)
            for tag in _active_occasion_tags(limit=9)
        ]
    else:
        subcategory_links = [
            _category_card(category)
            for category in _active_categories_for_section(section)
        ]

    context.update(
        {
            "section": section,
            "section_title": config["title"],
            "section_intro": config["intro"],
            "featured_items": featured_items,
            "occasion_cards": occasion_cards,
            "subcategory_links": subcategory_links,
            "flower_type_cards": flower_type_cards,
            "same_day_products": same_day_products,
            "section_more_url": _section_all_url(section),
            "featured_title": "Our Selection",
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
            "category_call_text": "Call for Guidance",
            "category_telegram_text": "تلگرام",
        }
    )

    return render(request, "category.html", context)

FLOWER_TYPE_SLUGS = [
    "hand-bouquet",
    "box",
    "bouquet",
    "jarl",
    "stand",
    "plants",
]

FLOWER_OCCASION_SLUGS = [
    "birthday",
    "romantic",
    "congratulation",
    "condolence",
    "formal-visit",
    "no-occasion",
]

FLOWER_TYPE_FALLBACK_IMAGES = {
    "hand-bouquet": "main/img/sub-bouquet.webp",
    "box": "main/img/sub-box.webp",
    "bouquet": "main/img/sub-bouquet.webp",
    "stand": "main/img/sub-stand.webp",
    "jarl": "main/img/sub-plant.webp",
    "plants": "main/img/sub-plant.webp",
    "wedding": "main/img/sub-bridal-bouquet.webp",
    "wedding-car": "main/img/sub-stand.webp",
    "bridal-bouquet": "main/img/sub-bridal-bouquet.webp",
}

OCCASION_FALLBACK_IMAGES = {
    "birthday": "main/img/occasions/birthday.webp",
    "romantic": "main/img/occasions/romantic.webp",
    "congratulation": "main/img/occasions/special.webp",
    "apology": "main/img/occasions/special.webp",
    "condolence": "main/img/occasions/condolence.webp",
    "proposal": "main/img/occasions/special.webp",
    "engagement": "main/img/occasions/special.webp",
    "formal-visit": "main/img/occasions/special.webp",
    "no-occasion": "main/img/occasions/special.webp",
}

def _sort_by_slug_order(items, slug_order):
    order_map = {slug: index for index, slug in enumerate(slug_order)}
    return sorted(items, key=lambda item: order_map.get(item.slug, 999))

def _flower_occasion_cards():
    tags = list(
        Tag.objects.for_general_catalog().filter(
            is_active=True,
            is_occasion=True,
            slug__in=FLOWER_OCCASION_SLUGS,
        ).order_by("sort_order", "name")
    )

    tags = _sort_by_slug_order(tags, FLOWER_OCCASION_SLUGS)

    cards = []

    for tag in tags:
        cards.append(
            {
                "slug": tag.slug,
                "label": tag.name,
                "url": reverse("flower_occasion", args=[tag.slug]),
                "image": (
                    tag.cover_image.url
                    if tag.cover_image
                    else OCCASION_FALLBACK_IMAGES.get(tag.slug, "main/img/occasions/special.webp")
                ),
            }
        )

    return cards

def _same_day_flower_products(limit=12):
    queryset = (
        _published_products_for_section(Category.Section.FLOWERS)
        .filter(tags__slug__in=SAME_DAY_TAG_SLUGS)
        .distinct()
        .order_by("sort_order", "-created_at")
    )
    # The admin selection is authoritative. If the seller removes every item,
    # the public same-day area must stay empty instead of showing ordinary flowers.
    return list(queryset[:limit])
