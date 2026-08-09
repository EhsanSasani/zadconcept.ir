"""Home HTTP views."""

from django.shortcuts import redirect, render

from ..content.catalog import SECTION_CONTENT
from ..selectors.catalog import active_occasion_tags, same_day_flower_products

from .support import (
    _default_context,
    _get_active_home_hero_slides,
    _occasion_card,
)

def index(request):
    legacy_section = (request.GET.get("section") or "").lower()

    if legacy_section in SECTION_CONTENT:
        return redirect(legacy_section)

    occasion_tags = active_occasion_tags(limit=4)

    context = _default_context(
        request,
        page_type="home",
        active_nav="home",
        meta_title="زاد | گل، سوئیت‌بار، هدیه و ورکشاپ در مشهد",
        meta_description="فروشگاه زاد در مشهد برای سفارش گل، سوئیت‌بار، هدیه، ورکشاپ و هماهنگی سریع ارسال.",
        enable_product_modal=True,
        content_page="home",
    )

    context.update(
        {
            "home_occasion_cards": [
                _occasion_card(tag) for tag in occasion_tags
            ],
            "home_hero_slides": _get_active_home_hero_slides(),
            "home_same_day_products": same_day_flower_products(),
        }
    )

    return render(request, "index.html", context)
