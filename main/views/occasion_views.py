from django.shortcuts import render

from ..catalog_selectors import _active_occasion_tags
from ..managed_heroes import _get_site_hero
from ..occasion_presentation import _occasion_card
from ..page_context import _default_context, _with_home
from ..page_presentation import _hero_from_key


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
