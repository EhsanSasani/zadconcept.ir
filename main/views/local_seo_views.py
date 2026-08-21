from django.shortcuts import render

from ..catalog_selectors import _published_products_for_section
from ..forms import LeadRequestForm
from ..managed_heroes import _get_site_hero
from ..models import Category
from ..page_context import _default_context, _with_home


def mashhad_hub(request):
    curated_items = list(
        _published_products_for_section(Category.Section.FLOWERS).order_by(
            "-featured",
            "sort_order",
            "-created_at",
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
            "lead_form": LeadRequestForm(initial_lead_type="flower"),
            "lead_default_type": "flower",
        }
    )

    return render(request, "mashhad_hub.html", context)
