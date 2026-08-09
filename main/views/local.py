"""Local landing HTTP views."""

from ..selectors.catalog import (
    active_root_categories,
    catalog_products_for_section,
    ordered_catalog_products,
)

from .support import (
    Category,
    Http404,
    _category_card,
    _default_context,
    _get_site_hero,
    _hero_from_key,
    _occasion_links,
    _with_home,
    render,
    reverse,
)

def mashhad_hub(request):
    curated_items = list(
        ordered_catalog_products(
            catalog_products_for_section(Category.Section.FLOWERS)
        )[:6]
    )

    breadcrumbs = _with_home([{"name": "Mashhad Orders", "url": None}])
    db_hero = _get_site_hero("mashhad")

    context = _default_context(
        request,
        page_type="local",
        active_nav="mashhad",
        meta_title="سفارش گل و ارسال در مشهد | زاد",
        meta_description="مرکز سفارش گل زاد در مشهد برای ارسال همان‌روز، بررسی موجودی و هماهنگی سریع.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="mashhad",
        suppress_default_hero=not db_hero,
    )

    if db_hero:
        context.update(db_hero)

    context.update(
        {
            "curated_items": curated_items,
        }
    )

    return render(request, "mashhad_hub.html", context)

def _local_landing(request, landing_type):
    if landing_type == "order":
        title = "سفارش گل در مشهد"
        subtitle = "انتخاب گل باکیفیت و هماهنگی سریع و شفاف برای ارسال در مشهد."
        meta_title = "سفارش گل در مشهد | زاد"
        meta_description = "سفارش گل در مشهد با پاسخ‌گویی سریع، چیدمان اختصاصی و هماهنگی تلفنی زاد."
    elif landing_type == "delivery":
        title = "ارسال همان‌روز گل در مشهد"
        subtitle = "هماهنگی ارسال همان‌روز با بسته‌بندی و استانداردهای زاد."
        meta_title = "ارسال همان‌روز گل در مشهد | زاد"
        meta_description = "ارسال همان‌روز گل در مشهد با پشتیبانی تلفنی و انتخاب از محصولات آماده زاد."
    else:
        raise Http404("Landing page not found")

    curated_items = list(
        ordered_catalog_products(
            catalog_products_for_section(Category.Section.FLOWERS)
        )[:8]
    )

    breadcrumbs = _with_home(
        [
            {"name": "Mashhad Orders", "url": reverse("mashhad_hub")},
            {"name": title, "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="local",
        active_nav="mashhad",
        meta_title=meta_title,
        meta_description=meta_description,
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
    )

    hero_data = _hero_from_key("mashhad", title=title, text=subtitle)
    target_slug = {
        "order": "flower-order",
        "delivery": "flower-delivery",
    }[landing_type]
    db_hero = _get_site_hero("mashhad", target_slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)

    occasion_links = _occasion_links(limit=4)

    if not occasion_links:
        occasion_links = [
            _category_card(category)
            for category in active_root_categories(Category.Section.FLOWERS)[:4]
        ]

    context.update(
        {
            "landing_title": title,
            "landing_subtitle": subtitle,
            "curated_items": curated_items,
            "why_zad": [
                "چیدمان مینیمال و متناسب با مناسبت",
                "پاسخ‌گویی سریع و هماهنگی شفاف پیش از ارسال",
                "امکان ارسال همان‌روز در محدوده‌های قابل پوشش مشهد",
                "بسته‌بندی حرفه‌ای و آماده هدیه",
            ],
            "occasion_links": occasion_links,
        }
    )

    return render(request, "local_landing.html", context)

def mashhad_flower_order(request):
    return _local_landing(request, "order")

def mashhad_flower_delivery(request):
    return _local_landing(request, "delivery")
