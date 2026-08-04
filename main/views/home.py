"""Home HTTP views.

Extracted from the historical view module; shared presentation policy remains in
``main.views.legacy`` until its dedicated lower layer is complete.
"""

from .support import (
    Category,
    Event,
    Product,
    PublishStatus,
    Q,
    SAME_DAY_TAG_SLUG,
    SECTION_CONTENT,
    _active_occasion_tags,
    _default_context,
    _get_active_home_hero_slides,
    _occasion_card,
    _published_products,
    redirect,
    render,
    timezone,
)

def index(request):
    legacy_section = (request.GET.get("section") or "").lower()

    if legacy_section in SECTION_CONTENT:
        return redirect(legacy_section)

    def pick_home_products(section, limit=2):
        return list(
            _published_products()
            .filter(category__section=section)
            .select_related("category")
            .prefetch_related("tags")
            .order_by("-featured", "sort_order", "-created_at")[:limit]
        )

    featured_today = (
        pick_home_products(Category.Section.FLOWERS, 6)
        + pick_home_products(Category.Section.BAKERY, 1)
        + pick_home_products(Category.Section.GIFTS, 1)
    )

    if len(featured_today) < 6:
        used_ids = [product.id for product in featured_today]

        fallback_products = list(
            _published_products()
            .exclude(id__in=used_ids)
            .select_related("category")
            .prefetch_related("tags")
            .order_by("-featured", "sort_order", "-created_at")[: 6 - len(featured_today)]
        )

        featured_today += fallback_products

    occasion_tags = _active_occasion_tags(limit=8)

    context = _default_context(
        request,
        page_type="home",
        active_nav="home",
        meta_title="زاد | گل، سوئیت‌بار، هدیه و ورکشاپ در مشهد",
        meta_description="فروشگاه زاد در مشهد برای سفارش گل، سوئیت‌بار، هدیه، ورکشاپ و هماهنگی سریع ارسال.",
        enable_product_modal=True,
    )

    home_events = list(
        Event.objects.filter(
            status=PublishStatus.PUBLISHED,
            end_at__gte=timezone.now(),
        ).order_by("start_at")[:3]
    )
    home_same_day_products = (
        Product.objects
        .filter(
            Q(tags__slug=SAME_DAY_TAG_SLUG)
            | Q(tags__slug="same-day")
            | Q(tags__name="ارسال روز")
            | Q(tags__name="ارسال فوری"),
            category__section=Category.Section.FLOWERS,
            is_active=True,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        .select_related("category")
        .prefetch_related("tags")
        .distinct()
        .order_by("sort_order", "-created_at")
    )
    context.update(
        {
            "featured_today": featured_today,
            "occasion_tags": occasion_tags,
            "home_occasion_cards": [
                _occasion_card(tag) for tag in occasion_tags[:4]
            ],
            "sections": SECTION_CONTENT,
            "hero_call_text": "Call Now",
            "hero_telegram_text": "تلگرام",
            "home_subtitle": "Premium flowers, bakery, and gifts with fast coordination in Mashhad",
            "is_homepage": True,
            "home_hero_slides": _get_active_home_hero_slides(),
            "home_events": home_events,
            "home_same_day_products": home_same_day_products,
        }
    )

    return render(request, "index.html", context)
