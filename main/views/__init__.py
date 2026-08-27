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
from .catalog_views import CATALOG_PAGE_SIZE, CATEGORY_SLUG_ALIASES, COLLECTION_LANDING_CONTENT, FLOWER_FILTER_ORDER, SECTION_ALL_ROUTE_NAMES, WEDDING_BAKERY_LEGACY_SLUGS, WEDDING_FLOWER_LEGACY_SLUGS, _catalog_ordered_products, _collection_landing_page, _filter_links_for_categories, _paginate_products, _section_all_products, _section_all_url, _section_subcategory, bakery, bakery_all, bakery_subcategory, flower_subcategory, flowers, flowers_all, flowers_same_day, gift_subcategory, gifts, gifts_all
from .wedding_views import WEDDING_COLLECTIONS, _managed_wedding_collection_content, _proposal_collection_filter_data, _published_wedding_products, _wedding_content_and_gallery, wedding_collection, weddings
from .section_views import FLOWER_OCCASION_SLUGS, FLOWER_TYPE_FALLBACK_IMAGES, FLOWER_TYPE_SLUGS, OCCASION_FALLBACK_IMAGES, _category_page, _featured_selection, _flower_occasion_cards, _flower_same_day_products, _flower_type_cards, _same_day_flower_products, _sort_by_slug_order
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



























# =========================
# Home
# =========================



# =========================
# Weddings
# =========================














# =========================
# Section pages
# =========================




















































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
