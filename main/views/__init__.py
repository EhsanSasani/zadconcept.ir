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
from .catalog_views import CATEGORY_SLUG_ALIASES, SECTION_ALL_ROUTE_NAMES, WEDDING_BAKERY_LEGACY_SLUGS, WEDDING_FLOWER_LEGACY_SLUGS, _filter_links_for_categories, _section_all_products, _section_all_url, _section_subcategory, bakery_all, bakery_subcategory, flower_subcategory, flowers_all, gift_subcategory, gifts_all
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







COLLECTION_LANDING_CONTENT = {
    Category.Section.FLOWERS: {
        "hero_eyebrow": "FLOWER COLLECTION",
        "hero_title": "استودیو گل زاد",
        "hero_text": "گل‌هایی برای تمام لحظه‌های خاص زندگی شما",
        "hero_image": "main/img/flowers-hero.webp",
        "fallback_image": "main/img/cat-flowers.webp",
        "empty_text": "هنوز محصولی برای نمایش ثبت نشده است.",
        "why_items": [
            {
                "icon": "bi bi-flower1",
                "title": "گل‌های تازه",
                "text": "انتخاب روزانه و چیدمان با دقت",
            },
            {
                "icon": "bi bi-gift",
                "title": "بسته‌بندی شیک",
                "text": "هماهنگ با حس و مناسبت سفارش",
            },
            {
                "icon": "bi bi-truck",
                "title": "ارسال در مشهد",
                "text": "هماهنگی سریع برای تحویل مطمئن",
            },
        ],
        "cta_kicker": "CUSTOM ORDER",
        "cta_title": "دسته‌گل اختصاصی، دقیقاً مطابق سلیقه شما",
        "cta_text": "برای انتخاب رنگ، سبک چیدمان، بودجه و زمان ارسال، با ما تماس بگیرید یا در تلگرام پیام بدهید.",
        "cta_image": "main/img/footer-floral.webp",
        "cta_alt": "سفارش اختصاصی گل",
    },
    Category.Section.BAKERY: {
        "hero_eyebrow": "ZAD SWEET BAR",
        "hero_title": "سوییت بار زاد",
        "hero_text": "طعم‌های شیرین برای لحظه‌های گرم و به‌یادماندنی",
        "hero_image": "main/img/hero-bakery.webp",
        "fallback_image": "main/img/cat-bakery.webp",
        "empty_text": "هنوز محصولی در سوییت بار ثبت نشده است.",
        "why_items": [
            {
                "icon": "bi bi-stars",
                "title": "تازه و خوش‌طعم",
                "text": "آماده‌سازی با مواد اولیه باکیفیت",
            },
            {
                "icon": "bi bi-gift",
                "title": "بسته‌بندی شیک",
                "text": "مناسب هدیه و پذیرایی‌های خاص",
            },
            {
                "icon": "bi bi-truck",
                "title": "ارسال در مشهد",
                "text": "هماهنگی سریع برای تحویل مطمئن",
            },
        ],
        "cta_kicker": "CUSTOM ORDER",
        "cta_title": "سفارش شیرینی اختصاصی، دقیقاً برای مناسبت شما",
        "cta_text": "برای انتخاب طعم، تعداد، نوع بسته‌بندی و زمان ارسال، با ما تماس بگیرید یا در تلگرام پیام بدهید.",
        "cta_image": "main/img/hero-bakery.webp",
        "cta_alt": "سفارش اختصاصی سوییت بار",
    },
    Category.Section.GIFTS: {
        "hero_eyebrow": "ZAD CONCEPT STORE",
        "hero_title": "کانسپت استور زاد",
        "hero_text": "هدیه‌هایی خاص برای آدم‌ها و لحظه‌های خاص زندگی شما",
        "hero_image": "main/img/hero-gifts-v2.webp",
        "fallback_image": "main/img/cat-gifts.webp",
        "empty_text": "هنوز محصولی در کانسپت استور ثبت نشده است.",
        "why_items": [
            {
                "icon": "bi bi-stars",
                "title": "انتخاب‌های خاص",
                "text": "محصولاتی مینیمال و انتخاب‌شده با دقت",
            },
            {
                "icon": "bi bi-gift",
                "title": "بسته‌بندی هدیه",
                "text": "هماهنگ با حس و مناسبت سفارش",
            },
            {
                "icon": "bi bi-truck",
                "title": "ارسال در مشهد",
                "text": "هماهنگی سریع برای تحویل مطمئن",
            },
        ],
        "cta_kicker": "CUSTOM GIFT",
        "cta_title": "هدیه‌ای خاص، دقیقاً مطابق سلیقه شما",
        "cta_text": "برای انتخاب هدیه، بسته‌بندی، بودجه و زمان ارسال، با ما تماس بگیرید یا در تلگرام پیام بدهید.",
        "cta_image": "main/img/gifts-custom-v1.webp",
        "cta_alt": "سفارش هدیه اختصاصی",
    },
}












# =========================
# Product / category helpers
# =========================

CATALOG_PAGE_SIZE = 12


def _catalog_ordered_products(queryset, section):
    if section == Category.Section.FLOWERS:
        order = {slug: index for index, slug in enumerate(FLOWER_FILTER_ORDER)}
        cases = [
            When(category__slug=slug, then=Value(index))
            for slug, index in order.items()
        ]
        queryset = queryset.annotate(
            category_rank=Case(
                *cases,
                default=Value(len(order)),
                output_field=IntegerField(),
            )
        )
        return queryset.order_by(
            "category_rank",
            "-featured",
            "sort_order",
            "-created_at",
            "id",
        )

    return queryset.order_by("-featured", "sort_order", "-created_at", "id")


def _paginate_products(request, queryset):
    paginator = Paginator(queryset, CATALOG_PAGE_SIZE)
    page_number = request.GET.get("page") or 1

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        raise Http404("Catalog page does not exist")

    return page_obj














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

SAME_DAY_TAG_SLUGS = [
    "same-day",
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


FLOWER_FILTER_ORDER = [
    "hand-bouquet",
    "box",
    "bouquet",
    "jarl",
    "stand",
    "plants",
]


def _collection_landing_page(
    request,
    section,
    *,
    excluded_category_slugs=(),
    directory_only=False,
):
    config = SECTION_CONTENT[section]
    landing = COLLECTION_LANDING_CONTENT[section]
    page = request.GET.get("page")

    if (
        directory_only
        and set(request.GET) == {"page"}
        and page
        and page.isdigit()
        and int(page) >= 1
    ):
        return redirect(reverse(section), permanent=True)
    products_qs = _published_products_for_section(section)
    categories_qs = Category.objects.for_general_catalog().filter(
        section=section,
        is_active=True,
    )
    if directory_only:
        categories_qs = categories_qs.filter(parent__isnull=True)

    if excluded_category_slugs:
        products_qs = products_qs.exclude(category__slug__in=excluded_category_slugs)
        categories_qs = categories_qs.exclude(slug__in=excluded_category_slugs)

    selected_category_slug = request.GET.get("category") or ""
    selected_category = None

    if selected_category_slug and directory_only:
        selected_category = get_object_or_404(
            categories_qs,
            slug=selected_category_slug,
        )
        return redirect(selected_category.get_absolute_url(), permanent=True)

    if selected_category_slug:
        selected_category = get_object_or_404(
            categories_qs,
            slug=selected_category_slug,
        )
        products_qs = products_qs.filter(category=selected_category)

    if directory_only:
        page_obj = None
        products = []
    else:
        products_qs = _catalog_ordered_products(products_qs, section)
        page_obj = _paginate_products(request, products_qs)
        products = list(page_obj.object_list)

    if request.GET.get("partial") == "products":
        if directory_only:
            raise Http404("The flowers landing page is a category directory")
        html = render_to_string(
            "partials/product_card.html",
            {
                "products": products,
                "card_variant": "landing",
                "fallback_image": landing["fallback_image"],
                "empty_text": landing["empty_text"],
            },
            request=request,
        )

        response = JsonResponse(
            {
                "html": html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Cache-Control"] = "no-store"
        return response

    categories = list(categories_qs.distinct().order_by("sort_order", "name"))
    if section == Category.Section.FLOWERS:
        order = {slug: index for index, slug in enumerate(FLOWER_FILTER_ORDER)}
        categories.sort(key=lambda category: order.get(category.slug, len(order)))

    catalog_filter_items = _filter_links_for_categories(
        reverse(section),
        categories,
        selected_slug=selected_category.slug if selected_category else None,
    )
    landing_category_cards = [_category_card(category) for category in categories]

    context = _default_context(
        request,
        page_type="flowers_landing",
        active_nav=config["nav"],
        meta_title=config["meta_title"],
        meta_description=config["meta_description"],
        breadcrumbs=None,
        enable_product_modal=not directory_only,
        content_page=section,
    )
    page_hero = _get_site_hero(section)
    context.update(page_hero or _hero_from_key(section))
    context.update(
        {
            "section": section,
            "catalog_products": products,
            "catalog_page_obj": page_obj,
            "catalog_filter_items": catalog_filter_items,
            "landing_category_cards": landing_category_cards,
            "directory_only": directory_only,
            "selected_category_slug": selected_category.slug if selected_category else "",
            "catalog_page_size": CATALOG_PAGE_SIZE,
            "catalog_load_url": reverse(section),
            "landing_hero_eyebrow": (
                page_hero["page_hero_kicker"]
                if page_hero
                else landing["hero_eyebrow"]
            ),
            "landing_hero_title": (
                page_hero["page_hero_title"]
                if page_hero
                else landing["hero_title"]
            ),
            "landing_hero_text": (
                page_hero["page_hero_text"]
                if page_hero
                else landing["hero_text"]
            ),
            "landing_hero_image": (
                page_hero["page_hero_image"]
                if page_hero
                else landing["hero_image"]
            ),
            "landing_hero_mobile_image": (
                page_hero["page_hero_mobile_image"] if page_hero else ""
            ),
            "landing_fallback_image": landing["fallback_image"],
            "landing_empty_text": landing["empty_text"],
            "landing_why_items": landing["why_items"],
            "landing_cta_kicker": landing["cta_kicker"],
            "landing_cta_title": landing["cta_title"],
            "landing_cta_text": landing["cta_text"],
            "landing_cta_image": landing["cta_image"],
            "landing_cta_alt": landing["cta_alt"],
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "flowers_landing.html", context)


def flowers(request):
    return _collection_landing_page(
        request,
        Category.Section.FLOWERS,
        directory_only=True,
    )


def bakery(request):
    return _collection_landing_page(request, Category.Section.BAKERY)


def gifts(request):
    return _collection_landing_page(request, Category.Section.GIFTS)



def flowers_same_day(request):
    products = (
        Product.objects.for_general_catalog()
        .published()
        .filter(
            category__section=Category.Section.FLOWERS,
            tags__slug__in=SAME_DAY_TAG_SLUGS,
        )
        .select_related("category")
        .prefetch_related("tags")
        .distinct()
        .order_by("sort_order", "-updated_at")
    )

    breadcrumbs = _with_home(
        [
            {"name": "گل‌ها", "url": reverse("flowers")},
            {"name": "ارسال امروز", "url": None},
        ]
    )
    context = _default_context(
        request,
        page_type="catalog",
        active_nav="flowers",
        meta_title="ارسال گل امروز در مشهد | زاد",
        meta_description=(
            "سفارش گل‌های آماده برای ارسال همان‌روز در مشهد؛ "
            "بررسی موجودی و هماهنگی سریع با زاد."
        ),
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="subcategory",
        schema_type="CollectionPage",
    )
    hero_data = {
        "page_hero_title": "ارسال امروز",
        "page_hero_text": "گل‌های آماده برای ارسال سریع در شهر مشهد.",
        "page_hero_image": "main/img/hero-about.webp",
    }
    db_hero = _get_site_hero("subcategory", "same-day")
    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
        "collection_title": "گل‌هایی برای همین امروز",
        "collection_kicker": "SAME DAY SELECTION",
        "collection_intro": (
            "منتخب‌هایی که آماده‌اند تا با هماهنگی سریع، "
            "همین امروز در مشهد به دست شما برسند."
        ),
        "subcategory_label": "ارسال امروز",
        "items": products,
        "is_same_day_page": True,
        }
    )
    context["structured_data_graph"].append(service_node(context["canonical_url"]))

    return render(request, "subcategory.html", context)




















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
