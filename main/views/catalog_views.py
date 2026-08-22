from ..category_presentation import _category_card
from ..catalog_selectors import _published_products
from ..models import BAKERY_WEDDING_CATEGORY_SLUGS, FLOWER_PROTECTED_WEDDING_CATEGORY_SLUGS, WEDDING_LEGACY_TAG_SLUGS
from ..page_presentation import _category_content

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..category_presentation import _section_category_url
from ..catalog_selectors import _published_products_for_section
from ..forms import LeadRequestForm
from ..managed_heroes import _get_site_hero
from ..models import Category
from ..page_context import _default_context, _with_home
from ..page_presentation import SECTION_CONTENT, _hero_from_key


SECTION_ALL_ROUTE_NAMES = {
    Category.Section.FLOWERS: "flowers_all",
    Category.Section.BAKERY: "bakery_all",
    Category.Section.GIFTS: "gifts_all",
}

def _section_all_url(section):
    route_name = SECTION_ALL_ROUTE_NAMES.get(section)

    if route_name:
        return reverse(route_name)

    return reverse(section)

def _filter_links_for_categories(
    base_url,
    categories,
    selected_slug=None,
    *,
    selected_section=None,
    include_section=False,
):
    links = [
        {
            "label": "همه",
            "slug": "all",
            "section": "",
            "filter_value": "all",
            "url": base_url,
            "is_active": not selected_slug,
        }
    ]

    for category in categories:
        filter_url = f"{base_url}?category={category.slug}"

        if include_section:
            filter_url += f"&section={category.section}"

        links.append(
            {
                "label": category.name,
                "slug": category.slug,
                "section": category.section,
                "filter_value": category.slug,
                "url": _section_category_url(category),
                "filter_url": filter_url,
                "is_active": (
                    selected_slug == category.slug
                    and (not include_section or selected_section == category.section)
                ),
            }
        )

    return links

def _section_all_products(request, section):
    config = SECTION_CONTENT[section]
    products_qs = _published_products_for_section(section).order_by(
        "-featured",
        "sort_order",
        "-created_at",
    )

    categories = list(
        Category.objects.for_general_catalog().filter(
            section=section,
            is_active=True,
            children__isnull=True,
        ).order_by("sort_order", "name")
    )

    selected_category = None
    selected_slug = request.GET.get("category") or ""

    if selected_slug:
        selected_category = get_object_or_404(
            Category.objects.for_general_catalog(),
            section=section,
            slug=selected_slug,
            is_active=True,
        )
        if selected_category.children.filter(is_active=True).exists():
            return redirect(selected_category.get_absolute_url(), permanent=True)
        products_qs = products_qs.filter(category=selected_category)

    items = list(products_qs[:48])
    title = config["title"]

    if selected_category:
        title = f"{config['title']} / {selected_category.name}"

    breadcrumbs = _with_home(
        [
            {"name": config["title"], "url": reverse(section)},
            {"name": "All Products", "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="subcategory",
        active_nav=config["nav"],
        meta_title=f"{title} در مشهد | زاد",
        meta_description=f"مشاهده و سفارش محصولات بخش {config['title']} زاد با هماهنگی ارسال در مشهد.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="subcategory",
    )

    hero_data = _hero_from_key(
        section,
        title=title,
        text="همه محصولات فعال این بخش را یک‌جا ببینید و برای موجودی و ارسال هماهنگ کنید.",
    )

    db_hero = _get_site_hero(section)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "collection_title": title,
            "collection_intro": config["intro"],
            "items": items,
            "filter_links": _filter_links_for_categories(
                _section_all_url(section),
                categories,
                selected_slug=selected_slug,
            ),
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "subcategory.html", context)

def flowers_all(request):
    return _section_all_products(request, Category.Section.FLOWERS)

def bakery_all(request):
    return _section_all_products(request, Category.Section.BAKERY)

def gifts_all(request):
    return _section_all_products(request, Category.Section.GIFTS)

CATEGORY_SLUG_ALIASES = {
    "plant": "plants",
    "wreath": "stand",
    "wedding-decoration": "wedding",
}

WEDDING_FLOWER_LEGACY_SLUGS = frozenset(
    (
        *FLOWER_PROTECTED_WEDDING_CATEGORY_SLUGS,
        *WEDDING_LEGACY_TAG_SLUGS,
    )
)

WEDDING_BAKERY_LEGACY_SLUGS = frozenset(
    (*BAKERY_WEDDING_CATEGORY_SLUGS, *WEDDING_LEGACY_TAG_SLUGS)
)

def _section_subcategory(request, section, subcategory_slug):
    category = get_object_or_404(
        Category.objects.for_general_catalog(),
        section=section,
        slug=subcategory_slug,
        is_active=True,
    )

    config = SECTION_CONTENT[section]
    content = _category_content(category)
    child_categories = list(
        category.children.filter(is_active=True).order_by("sort_order", "name")
    )

    visible_category_ids = [category.pk, *[child.pk for child in child_categories]]
    items = list(
        _published_products()
        .filter(category_id__in=visible_category_ids)
        .select_related("category")
        .prefetch_related("tags")
        .order_by("-featured", "sort_order", "-created_at")[:48]
    )

    breadcrumb_items = [{"name": config["title"], "url": reverse(section)}]
    if category.parent_id:
        breadcrumb_items.append(
            {"name": category.parent.name, "url": category.parent.get_absolute_url()}
        )
    breadcrumb_items.append({"name": category.name, "url": None})
    breadcrumbs = _with_home(breadcrumb_items)
    is_flower_category_page = section == Category.Section.FLOWERS
    db_hero = _get_site_hero("subcategory", category.slug)

    context = _default_context(
        request,
        page_type="subcategory",
        active_nav=config["nav"],
        meta_title=content["meta_title"],
        meta_description=content["meta_description"],
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="subcategory",
        suppress_default_hero=is_flower_category_page and not db_hero,
    )

    hero_data = _hero_from_key(
        "subcategory",
        title=content["label"],
        text=content["intro"],
        image=category.cover_image.url if category.cover_image else content["hero_image"],
    )

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "subcategory_slug": category.slug,
            "subcategory_label": category.name,
            "collection_title": category.name,
            "collection_intro": content["intro"],
            "is_flower_category_page": is_flower_category_page,
            "show_category_split_hero": is_flower_category_page and not db_hero,
            "category_hero_image": (
                category.cover_image.url if category.cover_image else content["image"]
            ),
            "category_parent_label": (
                category.parent.name if category.parent_id else ""
            ),
            "items": items,
            "child_categories": [
                _category_card(child) for child in child_categories
            ],
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "subcategory.html", context)

def flower_subcategory(request, subcategory_slug):
    if subcategory_slug in WEDDING_FLOWER_LEGACY_SLUGS:
        return redirect("weddings", permanent=True)

    canonical_slug = CATEGORY_SLUG_ALIASES.get(subcategory_slug, subcategory_slug)

    if canonical_slug != subcategory_slug:
        return redirect("flower_subcategory", subcategory_slug=canonical_slug)

    return _section_subcategory(request, Category.Section.FLOWERS, canonical_slug)

def bakery_subcategory(request, subcategory_slug):
    if subcategory_slug in WEDDING_BAKERY_LEGACY_SLUGS:
        return redirect("weddings", permanent=True)

    return _section_subcategory(request, Category.Section.BAKERY, subcategory_slug)

def gift_subcategory(request, subcategory_slug):
    return _section_subcategory(request, Category.Section.GIFTS, subcategory_slug)
