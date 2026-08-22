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
