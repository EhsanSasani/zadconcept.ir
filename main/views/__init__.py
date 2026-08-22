import hashlib
import json
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import DatabaseError, transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ..occasion_presentation import _occasion_card
from ..category_presentation import (
    SECTION_CATEGORY_ROUTE_NAMES,
    _category_card,
    _section_category_url,
)
from ..catalog_selectors import (
    _active_categories_for_section,
    _active_occasion_tags,
    _published_products,
    _published_products_for_section,
)
from .event_views import (
    event_detail,
    events,
)
from .static_page_views import (
    about,
    contact,
    faq,
)
from ..forms import LeadRequestForm
from .international_order_views import (
    international_orders,
    international_orders_en,
)
from .policy_views import (
    _normalized_policy,
    policy_page,
)
from .seo_views import (
    INDEXNOW_KEY_PATTERN,
    indexnow_key,
    robots_txt,
)
from .hero_style_views import (
    HERO_FONT_CSS_STACKS,
    _safe_hero_color,
    _safe_hero_font_url,
    _safe_hero_size,
    hero_styles_css,
)
from .security_views import (
    csp_report,
    security_logger,
)
from .error_views import custom_404
from .blog_views import blog, blog_detail
from .home_views import index
from .occasion_views import occasion_detail, occasions, flower_occasion
from .local_seo_views import (
    _local_landing,
    _occasion_links,
    mashhad_flower_delivery,
    mashhad_flower_order,
    mashhad_hub,
)
from .product_redirect_views import flower_detail, flower_detail_redirect, product_detail
from .catalog_views import CATALOG_PAGE_SIZE, CATEGORY_SLUG_ALIASES, COLLECTION_LANDING_CONTENT, FLOWER_FILTER_ORDER, SAME_DAY_TAG_SLUGS, SECTION_ALL_ROUTE_NAMES, WEDDING_BAKERY_LEGACY_SLUGS, WEDDING_FLOWER_LEGACY_SLUGS, _catalog_ordered_products, _collection_landing_page, _filter_links_for_categories, _paginate_products, _section_all_products, _section_all_url, _section_subcategory, bakery, bakery_all, bakery_subcategory, flower_subcategory, flowers, flowers_all, flowers_same_day, gift_subcategory, gifts, gifts_all
from .wedding_views import WEDDING_COLLECTIONS, _managed_wedding_collection_content, _proposal_collection_filter_data, _published_wedding_products, _wedding_content_and_gallery, wedding_collection, weddings
from .product_detail_views import _item_detail_context, _item_telegram_href, _section_product_detail, _telegram_href, bakery_product_detail, flower_product_detail, gift_product_detail
from ..telegram_notifications import send_lead_request_notification
from ..models import (
    BAKERY_WEDDING_CATEGORY_SLUGS,
    Category,
    Event,
    FLOWER_CATEGORY_SLUGS,
    FLOWER_PROTECTED_WEDDING_CATEGORY_SLUGS,
    HeroFont,
    HomeHeroSlide,
    NewsPost,
    PageContentBlock,
    Product,
    PROPOSAL_COLLECTION_TAG_SLUG,
    PublishStatus,
    SAME_DAY_TAG_SLUG,
    SiteHero,
    Tag,
    WEDDING_LEGACY_TAG_SLUGS,
    WeddingCollectionContent,
    WeddingPageContent,
    WorkshopPageContent,
)
from ..managed_heroes import (
    HERO_POSITION_VALUES,
    _get_active_home_hero_slides,
    _get_site_hero,
    _get_site_hero_slides,
    _hero_style_payload,
    _site_hero_payload,
)
from ..page_context import _default_context, _with_home
from ..page_presentation import (
    CATEGORY_CONTENT_OVERRIDES,
    FLOWER_STUDIO_NAME,
    LEGACY_FLOWER_BRAND_PHRASES,
    OCCASION_CARD_CONTENT,
    OCCASION_DETAIL_HERO_IMAGE,
    OCCASION_DETAIL_HERO_MOBILE_IMAGE,
    OCCASION_EN_LABELS,
    PAGE_HERO_CONTENT,
    SECTION_CONTENT,
    _category_content,
    _hero_defaults,
    _hero_from_key,
    _occasion_detail_hero,
    _public_brand_copy,
)
from ..seo import (
    article_node,
    base_graph,
    canonical_url,
    event_node,
    faq_node,
    product_node,
    robots_content,
    service_node,
    social_image_dimensions,
    social_image_url,
)
from ..site_content import (
    FAQ_PAGE_GROUPS,
    FAQ_PAGE_ITEMS,
    INTERNATIONAL_FAQ_EN,
    INTERNATIONAL_FAQ_FA,
    POLICY_PAGES,
)





# =========================
# Page content
# =========================



















# =========================
# Product / category helpers
# =========================



















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


# =========================
# Home
# =========================



# =========================
# Weddings
# =========================














# =========================
# Section pages
# =========================

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

































# =========================
# Product detail
# =========================

















# =========================
# Occasions
# =========================





# =========================
# Events
# =========================

# =========================
# Local SEO pages
# =========================









# =========================
# Static content pages
# =========================







# =========================
# Trust, policy, and international-order pages
# =========================





# =========================
# Blog
# =========================





# =========================
# Leads
# =========================

def _lead_rate_limited(request):
    # Nginx overwrites X-Real-IP before proxying through the private Unix socket.
    remote_address = request.META.get("HTTP_X_REAL_IP") or request.META.get(
        "REMOTE_ADDR", "unknown"
    )
    digest = hashlib.sha256(remote_address.encode("utf-8")).hexdigest()[:24]
    cache_key = f"lead-rate:{digest}"
    window = settings.LEAD_RATE_LIMIT_WINDOW
    limit = settings.LEAD_RATE_LIMIT_COUNT

    if cache.add(cache_key, 1, timeout=window):
        return False

    try:
        attempts = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=window)
        attempts = 1
    return attempts > limit

@require_POST
def submit_lead_request(request):
    include_event_fields = request.POST.get("lead_type") == "event"
    form = LeadRequestForm(request.POST, include_event_fields=include_event_fields)

    next_url = (
        request.POST.get("next")
        or request.META.get("HTTP_REFERER")
        or reverse("index")
    )

    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
    ):
        next_url = reverse("index")

    if _lead_rate_limited(request):
        messages.error(request, "تعداد درخواست‌ها زیاد است؛ چند دقیقه دیگر دوباره تلاش کنید.")
        return redirect(next_url)

    if form.is_valid():
        lead = form.save(commit=False)
        lead.source_page = request.POST.get("source_page", "")
        lead.save()
        transaction.on_commit(
            lambda lead_id=lead.pk: send_lead_request_notification(lead_id)
        )
        messages.success(
            request,
            "Your request has been submitted. zad will contact you soon.",
            extra_tags="lead-success",
        )
    else:
        messages.error(request, "Please complete the form correctly and try again.")

    return redirect(next_url)


# =========================
# SEO
# =========================
