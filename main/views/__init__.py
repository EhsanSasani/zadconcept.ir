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

WEDDING_COLLECTIONS = {
    "proposal-bouquets": {
        "type": Product.WeddingType.PROPOSAL_BOUQUET,
        "title": "دسته‌گل خواستگاری و بله‌برون",
        "short_title": "گل خواستگاری و بله‌برون",
        "kicker": "PROPOSAL BOUQUETS",
        "description": "دسته‌گل‌هایی هماهنگ با فضای خواستگاری و بله‌برون؛ با امکان هماهنگی رنگ، فرم و بودجه.",
        "fallback_image": "main/img/sub-bridal-bouquet.webp",
        "number": "01",
    },
    "proposal-sweets": {
        "type": Product.WeddingType.PROPOSAL_SWEETS,
        "title": "شیرینی خواستگاری و بله‌برون",
        "short_title": "شیرینی خواستگاری",
        "kicker": "PROPOSAL SWEETS",
        "description": "شیرینی‌های منتخب برای پذیرایی و هدیه، با امکان هماهنگی تعداد و چیدمان.",
        "fallback_image": "main/img/cat-bakery.webp",
        "number": "02",
    },
    "bridal-bouquets": {
        "type": Product.WeddingType.BRIDAL_BOUQUET,
        "title": "دسته‌گل عروس",
        "short_title": "دسته‌گل عروس",
        "kicker": "BRIDAL BOUQUETS",
        "description": "طراحی دسته‌گل عروس متناسب با استایل، فصل و پالت رنگ روز عروسی.",
        "fallback_image": "main/img/sub-bridal-bouquet.webp",
        "number": "03",
    },
    "wedding-cars": {
        "type": Product.WeddingType.WEDDING_CAR,
        "title": "ماشین عروس",
        "short_title": "ماشین عروس",
        "kicker": "WEDDING CARS",
        "description": "گل‌آرایی اختصاصی خودرو با توجه به مدل ماشین، فصل و سبک مراسم.",
        "fallback_image": "main/img/sub-stand.webp",
        "number": "04",
    },
}


def _published_wedding_products(wedding_type):
    wedding_products = list(
        Product.objects.valid_weddings()
        .published()
        .filter(wedding_type=wedding_type)
        .select_related("category")
        .prefetch_related("tags")
        .order_by(
            "wedding_sort_order",
            "sort_order",
            "-created_at",
            "id",
        )
    )

    if wedding_type != Product.WeddingType.PROPOSAL_BOUQUET:
        return wedding_products

    selected_general_products = _catalog_ordered_products(
        _published_products_for_section(Category.Section.FLOWERS)
        .filter(tags__slug=PROPOSAL_COLLECTION_TAG_SLUG)
        .distinct(),
        Category.Section.FLOWERS,
    )
    return wedding_products + list(selected_general_products)


def _proposal_collection_filter_data(request, products, collection_slug):
    general_products = [
        product
        for product in products
        if product.catalog_scope == Product.CatalogScope.GENERAL
    ]
    available_category_ids = {
        product.category_id for product in general_products if product.category_id
    }
    categories = list(
        Category.objects.for_general_catalog()
        .filter(
            pk__in=available_category_ids,
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        .order_by("sort_order", "name")
    )
    category_order = {
        slug: index for index, slug in enumerate(FLOWER_FILTER_ORDER)
    }
    categories.sort(
        key=lambda category: category_order.get(
            category.slug,
            len(category_order),
        )
    )

    selected_slug = request.GET.get("category") or ""
    selected_category = None
    filtered_products = products

    if selected_slug:
        selected_category = get_object_or_404(
            Category.objects.for_general_catalog(),
            section=Category.Section.FLOWERS,
            slug=selected_slug,
            is_active=True,
            pk__in=available_category_ids,
        )
        filtered_products = [
            product
            for product in general_products
            if product.category_id == selected_category.pk
        ]

    base_url = reverse("wedding_collection", args=[collection_slug])
    filter_links = (
        _filter_links_for_categories(
            base_url,
            categories,
            selected_slug=selected_slug,
        )
        if categories
        else []
    )
    return filtered_products, filter_links, selected_category


def _wedding_content_and_gallery():
    try:
        managed_content = WeddingPageContent.current()
    except DatabaseError:
        managed_content = None

    wedding_content = managed_content or WeddingPageContent()
    try:
        wedding_gallery = (
            list(wedding_content.gallery_images.all())
            if wedding_content.pk
            else []
        )
    except DatabaseError:
        wedding_gallery = []
    return wedding_content, wedding_gallery


def _managed_wedding_collection_content(collection_slug):
    try:
        return WeddingCollectionContent.objects.filter(
            collection_key=collection_slug
        ).first()
    except DatabaseError:
        return None


def weddings(request):
    wedding_content, wedding_gallery = _wedding_content_and_gallery()

    collections = []
    collection_products = []
    try:
        for slug, config in WEDDING_COLLECTIONS.items():
            products = _published_wedding_products(config["type"])
            collection_products.append(products)
            collections.append(
                {
                    **config,
                    "slug": slug,
                    "url": reverse("wedding_collection", args=[slug]),
                    "preview_product": products[0] if products else None,
                    "product_count": len(products),
                }
            )
    except DatabaseError:
        collections = [
            {
                **config,
                "slug": slug,
                "url": reverse("wedding_collection", args=[slug]),
                "preview_product": None,
                "product_count": 0,
            }
            for slug, config in WEDDING_COLLECTIONS.items()
        ]
        collection_products = []


    meta_title = (
        wedding_content.seo_title.strip()
        if wedding_content.seo_title
        else "محصولات عروسی، خواستگاری و بله‌برون در مشهد | زاد"
    )
    meta_description = (
        wedding_content.meta_description.strip()
        if wedding_content.meta_description
        else (
            "مجموعه اختصاصی زاد برای دسته‌گل عروس، گل‌آرایی ماشین عروس، "
            "دسته‌گل و شیرینی خواستگاری و بله‌برون در مشهد."
        )
    )
    social_image = wedding_content.open_graph_image or wedding_content.hero_image

    context = _default_context(
        request,
        page_type="weddings",
        active_nav="weddings",
        meta_title=meta_title,
        meta_description=meta_description,
        schema_type="CollectionPage",
        social_image=social_image or None,
        suppress_default_hero=True,
    )
    context.update(
        {
            "wedding_content": wedding_content,
            "wedding_gallery": wedding_gallery,
            "wedding_steps": wedding_content.steps,
            "wedding_collections": collections,
        }
    )
    return render(request, "weddings.html", context)


def wedding_collection(request, collection_slug):
    config = WEDDING_COLLECTIONS.get(collection_slug)
    if config is None:
        raise Http404("Wedding collection not found")

    managed_content = _managed_wedding_collection_content(collection_slug)
    try:
        products = _published_wedding_products(config["type"])
    except DatabaseError:
        products = []

    filter_links = []
    selected_category = None
    if config["type"] == Product.WeddingType.PROPOSAL_BOUQUET:
        products, filter_links, selected_category = _proposal_collection_filter_data(
            request,
            products,
            collection_slug,
        )

    if managed_content:
        hero_kicker = managed_content.hero_kicker
        hero_title = managed_content.hero_title
        hero_text = managed_content.hero_text
        hero_alt_text = managed_content.hero_alt_text
        hero_image = managed_content.hero_image or None
        hero_mobile_image = managed_content.hero_mobile_image or None
        managed_seo_title = (managed_content.seo_title or "").strip()
        managed_meta_description = (managed_content.meta_description or "").strip()
    else:
        hero_kicker = config["kicker"]
        hero_title = config["title"]
        hero_text = config["description"]
        hero_alt_text = config["title"]
        hero_image = None
        hero_mobile_image = None
        managed_seo_title = ""
        managed_meta_description = ""

    collection_data = {
        **config,
        "slug": collection_slug,
        "hero_kicker": hero_kicker,
        "hero_title": hero_title,
        "hero_text": hero_text,
        "hero_alt_text": hero_alt_text or config["title"],
        "hero_image": hero_image,
        "hero_mobile_image": hero_mobile_image,
    }
    collection_has_copy = any(
        value.strip() for value in (hero_kicker or "", hero_title or "", hero_text or "")
    )

    breadcrumbs = _with_home(
        [
            {"name": "عروسی", "url": reverse("weddings")},
            {"name": config["title"], "url": None},
        ]
    )
    meta_title = managed_seo_title or f"{config['title']} در مشهد | زاد"
    meta_description = managed_meta_description or config["description"]
    social_image = hero_image or (products[0].cover_image if products and products[0].cover_image else None)

    context = _default_context(
        request,
        page_type="wedding_collection",
        active_nav="weddings",
        meta_title=meta_title,
        meta_description=meta_description,
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        schema_type="CollectionPage",
        social_image=social_image,
        suppress_default_hero=True,
    )
    context.update(
        {
            "collection": collection_data,
            "collection_content": managed_content,
            "collection_has_copy": collection_has_copy,
            "products": products,
            "filter_links": filter_links,
            "selected_category": selected_category,
        }
    )
    return render(request, "wedding_collection.html", context)

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
