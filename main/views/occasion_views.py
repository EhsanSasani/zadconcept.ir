
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .catalog_views import _filter_links_for_categories
from ..catalog_selectors import _active_occasion_tags, _published_products, _published_products_for_section
from ..managed_heroes import _get_site_hero
from ..occasion_presentation import _occasion_card
from ..models import Category, Tag, WEDDING_LEGACY_TAG_SLUGS
from ..page_context import _default_context, _with_home
from ..page_presentation import OCCASION_CARD_CONTENT, SECTION_CONTENT, _hero_from_key, _occasion_detail_hero


def occasions(request):
    occasion_tags = _active_occasion_tags(limit=12)
    occasion_cards = [_occasion_card(tag) for tag in occasion_tags]
    breadcrumbs = _with_home(
        [
            {
                "name": "Occasions",
                "url": None,
            }
        ]
    )

    context = _default_context(
        request,
        page_type="occasions",
        active_nav="occasions",
        meta_title="انتخاب گل و هدیه براساس مناسبت | زاد",
        meta_description="انتخاب گل، سوئیت‌بار و هدیه زاد برای تولد، عاشقانه، تبریک، دلجویی و مناسبت‌های مختلف.",
        breadcrumbs=breadcrumbs,
    )

    hero_data = _hero_from_key("occasions")
    db_hero = _get_site_hero("occasions")

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "occasion_tags": occasion_tags,
            "occasion_cards": occasion_cards,
        }
    )

    return render(request, "occasions.html", context)


def flower_occasion(request, slug):
    if slug in WEDDING_LEGACY_TAG_SLUGS:
        return redirect("weddings", permanent=True)

    occasion = get_object_or_404(
        Tag.objects.for_general_catalog(),
        slug=slug,
        is_occasion=True,
        is_active=True,
    )

    card = OCCASION_CARD_CONTENT.get(occasion.slug, {})

    base_products_qs = (
        _published_products_for_section(Category.Section.FLOWERS)
        .filter(tags=occasion)
        .order_by("-featured", "sort_order", "-created_at")
    )

    available_category_ids = list(
        base_products_qs.values_list("category_id", flat=True).distinct()
    )

    available_categories = list(
        Category.objects.for_general_catalog().filter(
            pk__in=available_category_ids,
            is_active=True,
        ).order_by("sort_order", "name")
    )

    selected_slug = request.GET.get("category") or ""
    selected_category = None
    products_qs = base_products_qs

    if selected_slug:
        selected_category = get_object_or_404(
            Category.objects.for_general_catalog(),
            section=Category.Section.FLOWERS,
            slug=selected_slug,
            is_active=True,
            pk__in=available_category_ids,
        )
        products_qs = products_qs.filter(category=selected_category)

    products = list(products_qs[:48])
    suggested_sections = []

    for suggestion_section, title in (
        (Category.Section.BAKERY, "Matching Bakery"),
        (Category.Section.GIFTS, "Complementary Gifts"),
    ):
        section_products = list(
            _published_products_for_section(suggestion_section)
            .filter(tags=occasion)
            .order_by("-featured", "sort_order", "-created_at")[:6]
        )

        if section_products:
            suggested_sections.append(
                {
                    "title": title,
                    "products": section_products,
                    "more_url": reverse("occasion_detail", args=[occasion.slug]),
                }
            )

    title = card.get("hero_title") or f"{occasion.name} Flowers"

    if selected_category:
        title = f"{selected_category.name} / {card.get('title') or occasion.name}"

    breadcrumbs = _with_home(
        [
            {"name": "Flowers", "url": reverse("flowers")},
            {"name": occasion.name, "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="flower-occasion",
        active_nav="flowers",
        meta_title=f"{title} | سفارش در مشهد از زاد",
        meta_description=f"مشاهده انتخاب‌های {title} و هماهنگی سریع سفارش و ارسال در مشهد از زاد.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="occasion-detail",
    )

    hero_data = _occasion_detail_hero(occasion, title=title)

    db_hero = _get_site_hero("occasions", occasion.slug, allow_fallback=False)

    if db_hero:
        hero_data.update(db_hero)

    context.update(hero_data)

    base_url = reverse("flower_occasion", args=[occasion.slug])

    context.update(
        {
            "occasion": occasion,
            "products": products,
            "filter_links": _filter_links_for_categories(
                base_url,
                available_categories,
                selected_slug=selected_slug,
            ),
            "selected_category": selected_category,
            "suggested_sections": suggested_sections,
            "global_occasion_url": reverse("occasion_detail", args=[occasion.slug]),
            "is_flower_occasion": True,
        }
    )

    return render(request, "occasion_detail.html", context)

def occasion_detail(request, slug):
    if slug in WEDDING_LEGACY_TAG_SLUGS:
        return redirect("weddings", permanent=True)

    occasion = get_object_or_404(
        Tag.objects.for_general_catalog(),
        slug=slug,
        is_occasion=True,
        is_active=True,
    )

    card = OCCASION_CARD_CONTENT.get(occasion.slug, {})

    base_products_qs = (
        _published_products()
        .filter(tags=occasion)
        .select_related("category")
        .prefetch_related("tags")
        .order_by(
            "category__sort_order",
            "category__section",
            "category__name",
            "-featured",
            "sort_order",
            "-created_at",
        )
    )

    available_category_ids = list(
        base_products_qs.values_list("category_id", flat=True).distinct()
    )
    available_categories = list(
        Category.objects.for_general_catalog().filter(
            pk__in=available_category_ids,
            is_active=True,
        ).order_by("section", "sort_order", "name")
    )

    selected_slug = request.GET.get("category") or ""
    selected_section = request.GET.get("section") or ""
    selected_category = None
    products_qs = base_products_qs

    if selected_slug:
        category_lookup = {
            "slug": selected_slug,
            "is_active": True,
            "pk__in": available_category_ids,
        }

        if selected_section:
            category_lookup["section"] = selected_section

        selected_category = get_object_or_404(
            Category.objects.for_general_catalog(),
            **category_lookup,
        )
        products_qs = products_qs.filter(category=selected_category)

    products = list(products_qs[:48])

    suggested_sections = []

    for section, title in (
        (Category.Section.FLOWERS, "Flowers for this Mood"),
        (Category.Section.BAKERY, "Matching Bakery"),
        (Category.Section.GIFTS, "Complementary Gifts"),
    ):
        section_products = [
            product
            for product in products
            if product.category and product.category.section == section
        ][:8]

        if section_products:
            suggested_sections.append(
                {
                    "title": title,
                    "products": section_products,
                    "more_url": reverse(section) if section in SECTION_CONTENT else None,
                }
            )

    breadcrumbs = _with_home(
        [
            {
                "name": "Occasions",
                "url": reverse("occasions"),
            },
            {
                "name": occasion.name,
                "url": None,
            },
        ]
    )

    context = _default_context(
        request,
        page_type="occasion-detail",
        active_nav="occasions",
        meta_title=f"{occasion.name} | انتخاب گل و هدیه از زاد",
        meta_description=f"پیشنهادهای زاد برای {occasion.name}؛ انتخاب گل، هدیه و سوئیت‌بار با هماهنگی ارسال در مشهد.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
    )

    hero_data = _occasion_detail_hero(occasion)
    db_hero = _get_site_hero("occasions", occasion.slug, allow_fallback=False)

    if db_hero:
        hero_data.update(db_hero)

    context.update(hero_data)

    context.update(
        {
            "occasion": occasion,
            "products": products,
            "filter_links": _filter_links_for_categories(
                reverse("occasion_detail", args=[occasion.slug]),
                available_categories,
                selected_slug=selected_slug,
                selected_section=selected_section,
                include_section=True,
            ),
            "selected_category": selected_category,
            "suggested_sections": suggested_sections,
            "is_flower_occasion": False,
            "flower_occasion_url": reverse("flower_occasion", args=[occasion.slug]),
        }
    )

    return render(request, "occasion_detail.html", context)
