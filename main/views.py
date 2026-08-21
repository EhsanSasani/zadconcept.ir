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

from .catalog_selectors import (
    _active_categories_for_section,
    _active_occasion_tags,
    _published_products,
    _published_products_for_section,
)
from .forms import LeadRequestForm
from .telegram_notifications import send_lead_request_notification
from .models import (
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
from .page_presentation import (
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
from .seo import (
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
from .site_content import (
    FAQ_PAGE_GROUPS,
    FAQ_PAGE_ITEMS,
    INTERNATIONAL_FAQ_EN,
    INTERNATIONAL_FAQ_FA,
    POLICY_PAGES,
)


security_logger = logging.getLogger("main.security")

WEDDING_FLOWER_LEGACY_SLUGS = frozenset(
    (
        *FLOWER_PROTECTED_WEDDING_CATEGORY_SLUGS,
        *WEDDING_LEGACY_TAG_SLUGS,
    )
)
WEDDING_BAKERY_LEGACY_SLUGS = frozenset(
    (*BAKERY_WEDDING_CATEGORY_SLUGS, *WEDDING_LEGACY_TAG_SLUGS)
)


# =========================
# Page content
# =========================

CATEGORY_SLUG_ALIASES = {
    "plant": "plants",
    "wreath": "stand",
    "wedding-decoration": "wedding",
}


def _with_home(items):
    return [{"name": "Home", "url": reverse("index")}, *items]


def _telegram_href():
    return getattr(settings, "zad_TELEGRAM_URL", "https://t.me/Flowerhouse_pv")


def _item_telegram_href(request, product):
    return _telegram_href()


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


HERO_POSITION_VALUES = {
    "top-left",
    "top-center",
    "top-right",
    "center-left",
    "center",
    "center-right",
    "bottom-left",
    "bottom-center",
    "bottom-right",
}

HERO_FONT_CSS_STACKS = {
    "estedad": '"EstedadLocal", "VazirmatnLocal", Tahoma, sans-serif',
    "vazirmatn": '"VazirmatnLocal", "EstedadLocal", Tahoma, sans-serif',
    "cormorant": '"CormorantGaramond", "EstedadLocal", serif',
    "jakarta": '"PlusJakartaSans", "EstedadLocal", sans-serif',
}


def _hero_style_payload(hero, prefix):
    desktop_position = hero.content_position
    mobile_position = hero.mobile_content_position
    if desktop_position not in HERO_POSITION_VALUES:
        desktop_position = "center-left"
    if mobile_position not in HERO_POSITION_VALUES:
        mobile_position = "bottom-center"

    return {
        "style_class": f"hero-style-{prefix}-{hero.pk}",
        "content_position": desktop_position,
        "mobile_content_position": mobile_position,
    }


def _get_active_home_hero_slides():
    slides = list(
        HomeHeroSlide.objects.filter(is_active=True)
        .select_related("custom_font")
        .order_by("sort_order", "id")
    )

    if slides:
        return [
            {
                "title": _public_brand_copy(slide.title),
                "kicker": _public_brand_copy(slide.kicker),
                "description": _public_brand_copy(slide.description),
                "image_url": slide.image.url,
                "mobile_image_url": (
                    slide.mobile_image.url if slide.mobile_image else ""
                ),
                "primary_button_text": _public_brand_copy(
                    slide.primary_button_text
                ),
                "primary_button_url": slide.primary_button_url,
                "secondary_button_text": _public_brand_copy(
                    slide.secondary_button_text
                ),
                "secondary_button_url": slide.secondary_button_url,
                "show_content": bool(
                    slide.title
                    or slide.kicker
                    or slide.description
                    or (slide.primary_button_text and slide.primary_button_url)
                    or (slide.secondary_button_text and slide.secondary_button_url)
                ),
                **_hero_style_payload(slide, "home"),
            }
            for slide in slides
        ]

    return [
        {
            "title": "Flowers, Bakery & Gifts in Mashhad",
            "kicker": "zad Concept Store",
            "description": "Premium flowers, bakery, and gifts with fast coordination in Mashhad.",
            "image_url": settings.STATIC_URL + "main/img/hero-1.webp",
            "mobile_image_url": settings.STATIC_URL + "main/img/hero-mobile-1.webp",
            "primary_button_text": "Call Now",
            "primary_button_url": "",
            "secondary_button_text": "تلگرام",
            "secondary_button_url": "",
            "show_content": False,
            "style_class": "",
            "content_position": "bottom-right",
            "mobile_content_position": "bottom-center",
        },
        {
            "title": "Styled Details for Special Moments",
            "kicker": "Minimal & Premium",
            "description": "A polished zad experience across flowers, bakery, and gifts.",
            "image_url": settings.STATIC_URL + "main/img/hero-2.webp",
            "mobile_image_url": settings.STATIC_URL + "main/img/hero-mobile-2.webp",
            "primary_button_text": "",
            "primary_button_url": "",
            "secondary_button_text": "",
            "secondary_button_url": "",
            "show_content": False,
            "style_class": "",
            "content_position": "bottom-right",
            "mobile_content_position": "bottom-center",
        },
        {
            "title": "Fast Coordination in Mashhad",
            "kicker": "zad Mashhad",
            "description": "Quick coordination for urgent orders and daily selections.",
            "image_url": settings.STATIC_URL + "main/img/hero-3.webp",
            "mobile_image_url": settings.STATIC_URL + "main/img/hero-mobile-3.webp",
            "primary_button_text": "",
            "primary_button_url": "",
            "secondary_button_text": "",
            "secondary_button_url": "",
            "show_content": False,
            "style_class": "",
            "content_position": "bottom-right",
            "mobile_content_position": "bottom-center",
        },
    ]


def _site_hero_payload(hero):
    return {
        "kicker": _public_brand_copy(hero.kicker),
        "title": _public_brand_copy(hero.title),
        "text": _public_brand_copy(hero.description),
        "image": hero.image.url if hero.image else "main/img/hero-2.webp",
        "mobile_image": hero.mobile_image.url if hero.mobile_image else "",
        **_hero_style_payload(hero, "site"),
    }


def _get_site_hero_slides(target_page, target_slug="", *, allow_fallback=True):
    heroes = list(
        SiteHero.objects.filter(
            is_active=True,
            target_page=target_page,
            target_slug=target_slug,
        )
        .select_related("custom_font")
        .order_by("sort_order", "id")
    )

    if heroes:
        return [_site_hero_payload(hero) for hero in heroes]

    if target_slug and allow_fallback:
        fallback_heroes = list(
            SiteHero.objects.filter(
                is_active=True,
                target_page=target_page,
                target_slug="",
            )
            .select_related("custom_font")
            .order_by("sort_order", "id")
        )
        return [_site_hero_payload(hero) for hero in fallback_heroes]

    return []


def _get_site_hero(target_page, target_slug="", *, allow_fallback=True):
    slides = _get_site_hero_slides(
        target_page,
        target_slug,
        allow_fallback=allow_fallback,
    )
    if not slides:
        return None

    first = slides[0]
    return {
        "has_managed_site_hero": True,
        "page_hero_kicker": first["kicker"],
        "page_hero_title": first["title"],
        "page_hero_text": first["text"],
        "page_hero_image": first["image"],
        "page_hero_mobile_image": first["mobile_image"],
        "page_hero_slides": slides,
        "page_hero_style_class": first["style_class"],
        "page_hero_content_position": first["content_position"],
        "page_hero_mobile_content_position": first["mobile_content_position"],
    }


def _safe_hero_font_url(font):
    if not font or not font.font_file:
        return ""
    try:
        return font.font_file.url
    except Exception:
        # Storage backends can fail in different ways (missing object,
        # temporary network error, unsupported URL). Built-in fonts remain active.
        return ""


def _safe_hero_size(value, minimum, maximum, fallback):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return fallback
    return min(max(value, minimum), maximum)


def _safe_hero_color(value):
    value = str(value or "")
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.upper()
    return "#FFFFFF"


def hero_styles_css(request):
    """Serve database-backed Hero styling without unsafe inline CSS."""

    css_lines = ["/* ZAD dynamic Hero styles */"]

    try:
        fonts = list(HeroFont.objects.filter(is_active=True).order_by("id"))
        font_urls = {}
        format_map = {
            "woff2": "woff2",
            "woff": "woff",
            "ttf": "truetype",
            "otf": "opentype",
        }

        for font in fonts:
            font_url = _safe_hero_font_url(font)
            if not font_url:
                continue
            extension = font.font_file.name.rsplit(".", 1)[-1].lower()
            font_format = format_map.get(extension)
            if not font_format:
                continue
            font_urls[font.pk] = font_url
            css_lines.extend(
                [
                    "@font-face {",
                    f"  font-family: {json.dumps(font.css_family_name)};",
                    f"  src: url({json.dumps(font_url)}) format({json.dumps(font_format)});",
                    "  font-display: swap;",
                    "  font-style: normal;",
                    "  font-weight: 100 900;",
                    "}",
                ]
            )

        hero_groups = (
            (
                "home",
                HomeHeroSlide.objects.filter(is_active=True).select_related(
                    "custom_font"
                ),
            ),
            (
                "site",
                SiteHero.objects.filter(is_active=True).select_related("custom_font"),
            ),
        )

        for prefix, heroes in hero_groups:
            for hero in heroes:
                fallback_stack = HERO_FONT_CSS_STACKS.get(
                    hero.builtin_font,
                    HERO_FONT_CSS_STACKS["estedad"],
                )
                if hero.custom_font_id in font_urls:
                    font_stack = (
                        f'{json.dumps(hero.custom_font.css_family_name)}, {fallback_stack}'
                    )
                else:
                    font_stack = fallback_stack

                title_size = _safe_hero_size(hero.title_font_size, 28, 120, 64)
                body_size = _safe_hero_size(hero.body_font_size, 12, 32, 18)
                mobile_title_size = _safe_hero_size(
                    hero.mobile_title_font_size, 22, 72, 40
                )
                mobile_body_size = _safe_hero_size(
                    hero.mobile_body_font_size, 12, 24, 14
                )
                css_lines.extend(
                    [
                        f".hero-style-{prefix}-{hero.pk} {{",
                        f"  --hero-config-color: {_safe_hero_color(hero.text_color)};",
                        f"  --hero-config-font: {font_stack};",
                        f"  --hero-config-title-size: {title_size}px;",
                        f"  --hero-config-body-size: {body_size}px;",
                        f"  --hero-config-kicker-size: {max(11, round(body_size * 0.72))}px;",
                        f"  --hero-config-mobile-title-size: {mobile_title_size}px;",
                        f"  --hero-config-mobile-body-size: {mobile_body_size}px;",
                        f"  --hero-config-mobile-kicker-size: {max(10, round(mobile_body_size * 0.72))}px;",
                        "}",
                    ]
                )
    except DatabaseError:
        # A deploy that has not finished migrations still receives valid CSS.
        css_lines.append("/* Hero database is not ready; static fallbacks remain active. */")

    css = "\n".join(css_lines) + "\n"
    etag = f'"{hashlib.sha256(css.encode("utf-8")).hexdigest()}"'
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponse(status=304)
    else:
        response = HttpResponse(css, content_type="text/css; charset=utf-8")
    response["ETag"] = etag
    response["Cache-Control"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _default_context(
    request,
    *,
    page_type,
    active_nav,
    meta_title,
    meta_description,
    breadcrumbs=None,
    faq_items=None,
    include_faq_schema=False,
    item_id=None,
    enable_product_modal=False,
    content_page=None,
    schema_type="WebPage",
    og_type="website",
    social_image=None,
    language="fa-IR",
    html_lang="fa",
    html_dir="rtl",
    og_locale="fa_IR",
    alternate_links=None,
    hide_global_chrome=False,
    suppress_default_hero=False,
    is_indexable=True,
):
    page_canonical = canonical_url(request)
    structured_data_graph = base_graph(
        page_canonical,
        meta_title,
        meta_description,
        schema_type=schema_type,
        language=language,
    )
    social_width, social_height = social_image_dimensions(social_image)
    page_robots = robots_content(request) if is_indexable else "noindex,follow"
    context = {
        "page_type": page_type,
        "active_nav": active_nav,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "canonical_url": page_canonical,
        "robots_content": page_robots,
        "og_type": og_type,
        "og_locale": og_locale,
        "social_image_url": social_image_url(social_image),
        "social_image_width": social_width,
        "social_image_height": social_height,
        "item_id": item_id,
        "structured_data_graph": structured_data_graph,
        "is_homepage": False,
        "enable_product_modal": enable_product_modal,
        "flowers_url": reverse("flowers"),
        "html_lang": html_lang,
        "html_dir": html_dir,
        "alternate_links": alternate_links or [],
        "hide_global_chrome": hide_global_chrome,
        "suppress_default_hero": suppress_default_hero,
        "has_managed_site_hero": False,
        "page_content": {
            block.section_key: {
                "kicker": _public_brand_copy(block.kicker),
                "title": _public_brand_copy(block.title),
                "body": _public_brand_copy(block.body),
                "cta_text": _public_brand_copy(block.cta_text),
                "cta_url": block.cta_url,
            }
            for block in PageContentBlock.objects.filter(
                page=content_page or page_type,
                is_active=True,
            ).order_by("sort_order", "section_key")
        },
        **_hero_defaults(meta_title, meta_description),
    }

    if breadcrumbs:
        # Breadcrumb context is retained for a future visible UI component.
        # No BreadcrumbList JSON-LD is emitted while the visual breadcrumb is disabled.
        context["breadcrumbs"] = breadcrumbs

    if faq_items:
        context["faq_items"] = faq_items
        if include_faq_schema:
            structured_data_graph.append(
                faq_node(faq_items, page_canonical, language=language)
            )

    return context


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


SECTION_ALL_ROUTE_NAMES = {
    Category.Section.FLOWERS: "flowers_all",
    Category.Section.BAKERY: "bakery_all",
    Category.Section.GIFTS: "gifts_all",
}

SECTION_CATEGORY_ROUTE_NAMES = {
    Category.Section.FLOWERS: "flower_subcategory",
    Category.Section.BAKERY: "bakery_subcategory",
    Category.Section.GIFTS: "gift_subcategory",
}

def _section_all_url(section):
    route_name = SECTION_ALL_ROUTE_NAMES.get(section)

    if route_name:
        return reverse(route_name)

    return reverse(section)


def _section_category_url(category):
    route_name = SECTION_CATEGORY_ROUTE_NAMES.get(category.section)

    if route_name:
        return reverse(route_name, args=[category.slug])

    return reverse(category.section)


def _category_card(category):
    content = _category_content(category)
    has_children = category.children.filter(is_active=True).exists()

    return {
        "slug": category.slug,
        "label": category.name,
        "url": _section_category_url(category),
        "image": category.cover_image.url if category.cover_image else content["image"],
        "intro": category.description or content["intro"],
        "has_children": has_children,
    }


def _occasion_card(tag, *, for_flowers=False):
    content = OCCASION_CARD_CONTENT.get(tag.slug, {})
    url_name = "flower_occasion" if for_flowers else "occasion_detail"

    return {
        "slug": tag.slug,
        "label": content.get("title") or tag.name,
        "label_en": OCCASION_EN_LABELS.get(
            tag.slug,
            tag.slug.replace("-", " ").title(),
        ),
        "url": reverse(url_name, args=[tag.slug]),
        "image": (
            tag.cover_image.url
            if tag.cover_image
            else content.get(
                "image",
                "main/img/occasions/special.webp",
            )
        ),
        "intro": tag.description
        or content.get(
            "intro",
            "Curated ideas for this occasion.",
        ),
    }


def _occasion_links(limit=4):
    return [
        {
            "label": tag.name,
            "url": reverse("occasion_detail", args=[tag.slug]),
        }
        for tag in _active_occasion_tags(limit=limit)
    ]


def _featured_selection(queryset, limit=10):
    featured = list(queryset.filter(featured=True)[:limit])

    if len(featured) >= limit:
        return featured

    excluded_ids = [item.pk for item in featured]
    fallback = list(queryset.exclude(pk__in=excluded_ids)[: limit - len(featured)])

    return featured + fallback


def _filter_links_for_categories(
    base_url,
    categories,
    selected_slug=None,
    *,
    selected_section=None,
    include_section=False,
):
    links = [
        {
            "label": "همه",
            "slug": "all",
            "section": "",
            "filter_value": "all",
            "url": base_url,
            "is_active": not selected_slug,
        }
    ]

    for category in categories:
        filter_url = f"{base_url}?category={category.slug}"

        if include_section:
            filter_url += f"&section={category.section}"

        links.append(
            {
                "label": category.name,
                "slug": category.slug,
                "section": category.section,
                "filter_value": category.slug,
                "url": _section_category_url(category),
                "filter_url": filter_url,
                "is_active": (
                    selected_slug == category.slug
                    and (not include_section or selected_section == category.section)
                ),
            }
        )

    return links


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
        Product.objects.for_general_catalog()
        .published()
        .filter(
            Q(tags__slug=SAME_DAY_TAG_SLUG)
            | Q(tags__slug="same-day")
            | Q(tags__name="ارسال روز")
            | Q(tags__name="ارسال فوری"),
            category__section=Category.Section.FLOWERS,
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


def _section_all_products(request, section):
    config = SECTION_CONTENT[section]
    products_qs = _published_products_for_section(section).order_by(
        "-featured",
        "sort_order",
        "-created_at",
    )

    categories = list(
        Category.objects.for_general_catalog().filter(
            section=section,
            is_active=True,
            children__isnull=True,
        ).order_by("sort_order", "name")
    )

    selected_category = None
    selected_slug = request.GET.get("category") or ""

    if selected_slug:
        selected_category = get_object_or_404(
            Category.objects.for_general_catalog(),
            section=section,
            slug=selected_slug,
            is_active=True,
        )
        if selected_category.children.filter(is_active=True).exists():
            return redirect(selected_category.get_absolute_url(), permanent=True)
        products_qs = products_qs.filter(category=selected_category)

    items = list(products_qs[:48])
    title = config["title"]

    if selected_category:
        title = f"{config['title']} / {selected_category.name}"

    breadcrumbs = _with_home(
        [
            {"name": config["title"], "url": reverse(section)},
            {"name": "All Products", "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="subcategory",
        active_nav=config["nav"],
        meta_title=f"{title} در مشهد | زاد",
        meta_description=f"مشاهده و سفارش محصولات بخش {config['title']} زاد با هماهنگی ارسال در مشهد.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="subcategory",
    )

    hero_data = _hero_from_key(
        section,
        title=title,
        text="همه محصولات فعال این بخش را یک‌جا ببینید و برای موجودی و ارسال هماهنگ کنید.",
    )

    db_hero = _get_site_hero(section)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "collection_title": title,
            "collection_intro": config["intro"],
            "items": items,
            "filter_links": _filter_links_for_categories(
                _section_all_url(section),
                categories,
                selected_slug=selected_slug,
            ),
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "subcategory.html", context)

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

def flowers_all(request):
    return _section_all_products(request, Category.Section.FLOWERS)


def bakery_all(request):
    return _section_all_products(request, Category.Section.BAKERY)


def gifts_all(request):
    return _section_all_products(request, Category.Section.GIFTS)





def _section_subcategory(request, section, subcategory_slug):
    category = get_object_or_404(
        Category.objects.for_general_catalog(),
        section=section,
        slug=subcategory_slug,
        is_active=True,
    )

    config = SECTION_CONTENT[section]
    content = _category_content(category)
    child_categories = list(
        category.children.filter(is_active=True).order_by("sort_order", "name")
    )

    visible_category_ids = [category.pk, *[child.pk for child in child_categories]]
    items = list(
        _published_products()
        .filter(category_id__in=visible_category_ids)
        .select_related("category")
        .prefetch_related("tags")
        .order_by("-featured", "sort_order", "-created_at")[:48]
    )

    breadcrumb_items = [{"name": config["title"], "url": reverse(section)}]
    if category.parent_id:
        breadcrumb_items.append(
            {"name": category.parent.name, "url": category.parent.get_absolute_url()}
        )
    breadcrumb_items.append({"name": category.name, "url": None})
    breadcrumbs = _with_home(breadcrumb_items)
    is_flower_category_page = section == Category.Section.FLOWERS
    db_hero = _get_site_hero("subcategory", category.slug)

    context = _default_context(
        request,
        page_type="subcategory",
        active_nav=config["nav"],
        meta_title=content["meta_title"],
        meta_description=content["meta_description"],
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="subcategory",
        suppress_default_hero=is_flower_category_page and not db_hero,
    )

    hero_data = _hero_from_key(
        "subcategory",
        title=content["label"],
        text=content["intro"],
        image=category.cover_image.url if category.cover_image else content["hero_image"],
    )

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "subcategory_slug": category.slug,
            "subcategory_label": category.name,
            "collection_title": category.name,
            "collection_intro": content["intro"],
            "is_flower_category_page": is_flower_category_page,
            "show_category_split_hero": is_flower_category_page and not db_hero,
            "category_hero_image": (
                category.cover_image.url if category.cover_image else content["image"]
            ),
            "category_parent_label": (
                category.parent.name if category.parent_id else ""
            ),
            "items": items,
            "child_categories": [
                _category_card(child) for child in child_categories
            ],
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "subcategory.html", context)


def flower_subcategory(request, subcategory_slug):
    if subcategory_slug in WEDDING_FLOWER_LEGACY_SLUGS:
        return redirect("weddings", permanent=True)

    canonical_slug = CATEGORY_SLUG_ALIASES.get(subcategory_slug, subcategory_slug)

    if canonical_slug != subcategory_slug:
        return redirect("flower_subcategory", subcategory_slug=canonical_slug)

    return _section_subcategory(request, Category.Section.FLOWERS, canonical_slug)


def bakery_subcategory(request, subcategory_slug):
    if subcategory_slug in WEDDING_BAKERY_LEGACY_SLUGS:
        return redirect("weddings", permanent=True)

    return _section_subcategory(request, Category.Section.BAKERY, subcategory_slug)


def gift_subcategory(request, subcategory_slug):
    return _section_subcategory(request, Category.Section.GIFTS, subcategory_slug)


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


# =========================
# Product detail
# =========================

def _item_detail_context(request, product):
    category = product.category
    category_name = category.name if category else "Product"
    section = category.section if category else ""
    subcategory_url = None
    subcategory_label = None
    breadcrumbs = [{"name": "Home", "url": reverse("index")}]

    if product.is_wedding:
        active_nav = "weddings"
        section_label = "Weddings"
        category_url = reverse("weddings")
        breadcrumbs.append({"name": "عروسی", "url": category_url})

        wedding_related = (
            Product.objects.valid_weddings()
            .published()
            .exclude(pk=product.pk)
            .select_related("category")
            .prefetch_related("tags")
        )
        similar_items = list(
            wedding_related.filter(wedding_type=product.wedding_type).order_by(
                "wedding_sort_order",
                "sort_order",
                "-created_at",
                "id",
            )[:6]
        )
        if len(similar_items) < 6:
            extra_items = list(
                wedding_related.exclude(
                    pk__in=[item.pk for item in similar_items]
                ).order_by(
                    "wedding_sort_order",
                    "sort_order",
                    "-created_at",
                    "id",
                )[: 6 - len(similar_items)]
            )
            similar_items.extend(extra_items)
    else:
        active_nav = section if section in SECTION_CONTENT else ""
        section_label = (
            SECTION_CONTENT[section]["nav"].title()
            if section in SECTION_CONTENT
            else "Collection"
        )
        category_url = (
            reverse(section) if section in SECTION_CONTENT else reverse("index")
        )

        if category and category.section in SECTION_CATEGORY_ROUTE_NAMES:
            subcategory_url = _section_category_url(category)
            subcategory_label = category.name

        if section and section in SECTION_CONTENT:
            breadcrumbs.append(
                {
                    "name": SECTION_CONTENT[section]["title"],
                    "url": category_url,
                }
            )

        if category and category.parent_id:
            breadcrumbs.append(
                {
                    "name": category.parent.name,
                    "url": _section_category_url(category.parent),
                }
            )

        if subcategory_url and subcategory_label:
            breadcrumbs.append(
                {
                    "name": subcategory_label,
                    "url": subcategory_url,
                }
            )

        similar_items = list(
            _published_products()
            .filter(category=category)
            .exclude(pk=product.pk)
            .select_related("category")
            .prefetch_related("tags")
            .order_by("-featured", "sort_order", "-created_at")[:6]
        )

        if len(similar_items) < 3 and section:
            extra_items = list(
                _published_products()
                .filter(category__section=section)
                .exclude(pk=product.pk)
                .exclude(pk__in=[item.pk for item in similar_items])
                .select_related("category")
                .prefetch_related("tags")
                .order_by("-featured", "sort_order", "-created_at")[
                    : 6 - len(similar_items)
                ]
            )
            similar_items.extend(extra_items)

    breadcrumbs.append({"name": product.seo_name, "url": None})

    description = product.seo_description

    context = _default_context(
        request,
        page_type="item",
        active_nav=active_nav,
        meta_title=f"{product.seo_name} | سفارش در مشهد",
        meta_description=product.seo_description,
        breadcrumbs=breadcrumbs,
        item_id=product.pk,
        enable_product_modal=True,
        content_page="product",
        schema_type="ItemPage",
        og_type="product",
        social_image=product.cover_image if product.cover_image else None,
    )

    hero_data = _hero_from_key(
        "item",
        title=product.seo_name,
        text=description,
        image=product.cover_image.url if getattr(product, "cover_image", None) else "main/img/hero-gifts.webp",
    )

    db_hero = _get_site_hero("item", product.slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "product": product,
            "product_tags": product.tags.filter(is_active=True).order_by(
                "sort_order",
                "name",
            ),
            "category_name": category_name,
            "section_label": section_label,
            "category_url": category_url,
            "subcategory_url": subcategory_url,
            "subcategory_label": subcategory_label,
            "similar_items": similar_items,
            "item_telegram_href": _item_telegram_href(request, product),
            "item_call_text": "تماس",
            "item_telegram_text": "تلگرام",
            "mashhad_order_url": reverse("mashhad_flower_order"),
        }
    )

    if product.has_price:
        context["structured_data_graph"].append(product_node(product))

    return context


def product_detail(request, pk: int, slug: str):
    product = get_object_or_404(
        Product.objects.published()
        .select_related("category", "category__parent")
        .prefetch_related("tags", "gallery_images"),
        pk=pk,
    )

    return redirect(product.get_absolute_url(), permanent=True)


def _section_product_detail(request, section, category_slug, slug):
    products = (
        Product.objects.published()
        .select_related("category", "category__parent")
        .prefetch_related("tags", "gallery_images")
    )

    # Preserve the existing SEO/canonical contract: the current product slug
    # remains the primary public identifier. product_code is accepted only as
    # a stable, human-facing alias and is permanently redirected to canonical.
    try:
        product = products.get(slug=slug)
    except Product.DoesNotExist:
        product = get_object_or_404(products, product_code=slug)

    canonical_section = product.canonical_section or product.category.section
    canonical_category_slug = (
        product.canonical_category_slug or product.category.slug
    )
    if (
        slug != product.slug
        or canonical_section != section
        or canonical_category_slug != category_slug
    ):
        return redirect(product.get_absolute_url(), permanent=True)

    return render(request, "item_detail.html", _item_detail_context(request, product))


def flower_product_detail(request, category_slug, slug):
    return _section_product_detail(request, Category.Section.FLOWERS, category_slug, slug)


def bakery_product_detail(request, category_slug, slug):
    return _section_product_detail(request, Category.Section.BAKERY, category_slug, slug)


def gift_product_detail(request, category_slug, slug):
    return _section_product_detail(request, Category.Section.GIFTS, category_slug, slug)


def flower_detail(request, pk: int, slug: str):
    flower = get_object_or_404(
        Product.objects.published()
        .filter(category__section=Category.Section.FLOWERS)
        .select_related("category")
        .prefetch_related("tags", "gallery_images"),
        pk=pk,
    )

    return redirect(flower.get_absolute_url(), permanent=True)


def flower_detail_redirect(request, pk: int):
    flower = get_object_or_404(
        Product.objects.published().filter(
            category__section=Category.Section.FLOWERS,
        ),
        pk=pk,
    )

    return redirect(flower.get_absolute_url(), permanent=True)


# =========================
# Occasions
# =========================

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


# =========================
# Events
# =========================

def events(request):
    published_events = Event.objects.filter(
        status=PublishStatus.PUBLISHED,
        end_at__gte=timezone.now(),
    ).order_by("start_at", "-created_at")

    breadcrumbs = _with_home([{"name": "ورکشاپ‌ها", "url": None}])

    context = _default_context(
        request,
        page_type="workshops",
        active_nav="events",
        meta_title="ورکشاپ‌های خلاق و تجربه‌محور زاد در مشهد",
        meta_description=(
            "اطلاعات و ثبت درخواست ورکشاپ‌های عمومی، خصوصی و سازمانی زاد "
            "در مشهد؛ تجربه‌ای عملی برای ساختن، انتخاب‌کردن و خلق اثری شخصی."
        ),
        breadcrumbs=breadcrumbs,
    )

    page_hero = _get_site_hero("events")
    workshop_copy = WorkshopPageContent.current() or WorkshopPageContent()

    if page_hero:
        context.update(page_hero)

    context.update(
        {
            "workshops_hero_kicker": (
                page_hero["page_hero_kicker"]
                if page_hero
                else "ZAD WORKSHOPS"
            ),
            "workshops_hero_title": (
                page_hero["page_hero_title"]
                if page_hero
                else "ورکشاپ‌های زاد"
            ),
            "workshops_hero_text": (
                page_hero["page_hero_text"]
                if page_hero
                else (
                    "فضایی برای کار با دست‌ها، انتخاب و ترکیب متریال "
                    "و ساختن اثری شخصی در کنار دیگران."
                )
            ),
            "workshops_hero_image": (
                page_hero["page_hero_image"]
                if page_hero
                else "main/img/workshops-hero.webp"
            ),
            "workshops_hero_mobile_image": (
                page_hero["page_hero_mobile_image"] if page_hero else ""
            ),
            "events": published_events,
            "workshop_copy": workshop_copy,
            "lead_form": LeadRequestForm(
                initial_lead_type="event",
                include_event_fields=True,
            ),
            "lead_default_type": "event",
        }
    )

    return render(request, "events.html", context)


def event_detail(request, slug: str):
    event = get_object_or_404(
        Event,
        slug=slug,
        status=PublishStatus.PUBLISHED,
    )

    breadcrumbs = _with_home(
        [
            {"name": "Events", "url": reverse("events")},
            {"name": event.title, "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="category",
        active_nav="events",
        meta_title=f"{event.title} | ورکشاپ زاد",
        meta_description=f"جزئیات، زمان، مکان و هماهنگی حضور در {event.title} از ورکشاپ‌های زاد.",
        breadcrumbs=breadcrumbs,
        content_page="event-detail",
        og_type="article",
        social_image=event.cover_image if event.cover_image else None,
    )

    hero_data = _hero_from_key(
        "events",
        title=event.title,
        text=event.description,
        image=event.cover_image.url if event.cover_image else "main/img/hero-events.webp",
    )

    db_hero = _get_site_hero("events", event.slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)

    context.update(
        {
            "event": event,
            "lead_form": LeadRequestForm(
                initial_lead_type="event",
                include_event_fields=True,
            ),
            "lead_default_type": "event",
        }
    )

    context["structured_data_graph"].append(event_node(event))

    return render(request, "event_detail.html", context)


# =========================
# Local SEO pages
# =========================

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
        _published_products_for_section(Category.Section.FLOWERS).order_by(
            "-featured",
            "sort_order",
            "-created_at",
        )[:8]
    )

    local_faq = [
        {
            "question": "کدام محدوده‌های مشهد برای سفارش فوری پوشش داده می‌شوند؟",
            "answer": "بیشتر محدوده‌های شهری مشهد در ساعات کاری قابل بررسی‌اند و امکان دقیق پس از دریافت نشانی تأیید می‌شود.",
        },
        {
            "question": "برای ارسال همان‌روز چقدر زودتر هماهنگ کنم؟",
            "answer": "بهتر است حداقل دو تا سه ساعت زودتر پیام بدهید؛ امکان نهایی به موجودی و ظرفیت آماده‌سازی بستگی دارد.",
        },
        {
            "question": "آیا قبل از ارسال تصویر نهایی را دریافت می‌کنم؟",
            "answer": "در صورت درخواست، امکان هماهنگی برای ارسال تصویر نهایی پیش از تحویل وجود دارد.",
        },
    ]

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
        content_page="mashhad",
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
            for category in _active_categories_for_section(Category.Section.FLOWERS)[:4]
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
            "lead_form": LeadRequestForm(initial_lead_type="flower"),
            "lead_default_type": "flower",
        }
    )

    return render(request, "local_landing.html", context)


def mashhad_flower_order(request):
    return _local_landing(request, "order")


def mashhad_flower_delivery(request):
    return _local_landing(request, "delivery")


# =========================
# Static content pages
# =========================

def contact(request):
    breadcrumbs = _with_home([{"name": "Contact", "url": None}])

    context = _default_context(
        request,
        page_type="contact",
        active_nav="",
        meta_title="تماس با زاد | هماهنگی سفارش و ارسال",
        meta_description="تماس با زاد برای سفارش، مشاوره، بررسی موجودی و هماهنگی زمان ارسال در مشهد.",
        breadcrumbs=breadcrumbs,
    )

    hero_data = _hero_from_key("contact")
    db_hero = _get_site_hero("contact")

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "lead_form": LeadRequestForm(initial_lead_type="flower"),
            "lead_default_type": "flower",
        }
    )

    return render(request, "contact.html", context)


def faq(request):
    breadcrumbs = _with_home([{"name": "FAQ", "url": None}])

    context = _default_context(
        request,
        page_type="category",
        active_nav="",
        meta_title="سوالات متداول سفارش و ارسال | زاد",
        meta_description="پاسخ سوالات متداول درباره سفارش محصولات زاد، ارسال، ساعت کاری و هماهنگی ورکشاپ‌ها.",
        breadcrumbs=breadcrumbs,
        faq_items=FAQ_PAGE_ITEMS,
        include_faq_schema=True,
        content_page="faq",
    )

    hero_data = _hero_from_key("faq")
    db_hero = _get_site_hero("faq")

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context["faq_page_groups"] = FAQ_PAGE_GROUPS

    return render(request, "faq.html", context)


def about(request):
    breadcrumbs = _with_home([{"name": "About", "url": None}])

    context = _default_context(
        request,
        page_type="about",
        active_nav="about",
        meta_title="درباره زاد | گل، سوئیت‌بار و ورکشاپ در مشهد",
        meta_description="با فضای واقعی زاد، گل‌ها، سوئیت‌بار و ورکشاپ‌های خلاقانه زاد در مشهد آشنا شوید.",
        breadcrumbs=breadcrumbs,
    )

    hero_data = _hero_from_key("about")
    db_hero = _get_site_hero("about")

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "about_hero_kicker": (
                db_hero["page_hero_kicker"]
                if db_hero
                else "ZAD CONCEPT STORE · MASHHAD"
            ),
            "about_hero_title": (
                db_hero["page_hero_title"]
                if db_hero
                else "زاد؛ جایی برای گل، طعم، هدیه و تجربه."
            ),
            "about_hero_text": (
                db_hero["page_hero_text"]
                if db_hero
                else "یک فضای واقعی برای انتخاب‌های دقیق؛ از گل‌های روز و سوئیت‌بار تا ورکشاپ‌هایی که آدم‌ها را دور یک میز جمع می‌کنند."
            ),
            "about_hero_image": (
                db_hero["page_hero_image"]
                if db_hero
                else "main/img/about/zad-floral-wall-v1.webp"
            ),
            "about_hero_mobile_image": (
                db_hero["page_hero_mobile_image"] if db_hero else ""
            ),
        }
    )

    return render(request, "about.html", context)


# =========================
# Trust, policy, and international-order pages
# =========================

def _normalized_policy(policy):
    """Return template-safe policy data, including explicit empty item lists."""

    normalized_sections = []
    for section in policy.get("sections", []):
        paragraphs = section.get("paragraphs") or []
        items = section.get("items") or []
        if isinstance(paragraphs, str):
            paragraphs = [paragraphs]
        if isinstance(items, str):
            items = [items]
        normalized_sections.append(
            {
                "title": section.get("title", ""),
                "paragraphs": list(paragraphs),
                # The explicit key prevents Django templates from resolving the
                # missing value to dict.items(), which rendered raw tuples.
                "items": list(items),
            }
        )

    return {**policy, "sections": normalized_sections}


def policy_page(request, policy_slug):
    policy = POLICY_PAGES.get(policy_slug)
    if not policy:
        raise Http404("Policy page not found")

    breadcrumbs = _with_home([{"name": policy["title"], "url": None}])
    context = _default_context(
        request,
        page_type="policy",
        active_nav="",
        meta_title=policy["meta_title"],
        meta_description=policy["meta_description"],
        breadcrumbs=breadcrumbs,
        content_page="policy",
        suppress_default_hero=True,
    )
    context["policy"] = _normalized_policy(policy)
    return render(request, "policy_page.html", context)


def international_orders(request):
    fa_url = f"{settings.ZAD_SITE_URL}{reverse('international_orders')}"
    en_url = f"{settings.ZAD_SITE_URL}{reverse('international_orders_en')}"
    context = _default_context(
        request,
        page_type="policy",
        active_nav="",
        meta_title="سفارش گل از خارج ایران برای مشهد | زاد",
        meta_description="ثبت سفارش گل و هدیه از خارج ایران با پرداخت ارزی و تحویل محلی برای گیرنده در مشهد.",
        faq_items=INTERNATIONAL_FAQ_FA,
        include_faq_schema=True,
        alternate_links=[
            {"language": "fa", "url": fa_url},
            {"language": "en", "url": en_url},
            {"language": "x-default", "url": fa_url},
        ],
        content_page="international-orders",
        suppress_default_hero=True,
    )
    return render(request, "international_orders.html", context)


def international_orders_en(request):
    fa_url = f"{settings.ZAD_SITE_URL}{reverse('international_orders')}"
    en_url = f"{settings.ZAD_SITE_URL}{reverse('international_orders_en')}"
    context = _default_context(
        request,
        page_type="policy",
        active_nav="",
        meta_title="Send Flowers to Mashhad, Iran | ZAD",
        meta_description="Order flowers, gifts, and bakery items from abroad for local delivery to your recipient in Mashhad, Iran.",
        faq_items=INTERNATIONAL_FAQ_EN,
        include_faq_schema=True,
        language="en",
        html_lang="en",
        html_dir="ltr",
        og_locale="en_US",
        alternate_links=[
            {"language": "fa", "url": fa_url},
            {"language": "en", "url": en_url},
            {"language": "x-default", "url": fa_url},
        ],
        hide_global_chrome=True,
        suppress_default_hero=True,
        content_page="international-orders",
    )
    return render(request, "international_orders_en.html", context)


# =========================
# Blog
# =========================

def blog(request):
    posts = list(
        NewsPost.objects.filter(
            status=PublishStatus.PUBLISHED,
        ).order_by("-published_at", "-created_at")
    )

    breadcrumbs = _with_home([{"name": "Journal", "url": None}])
    db_hero = _get_site_hero("blog")

    context = _default_context(
        request,
        page_type="category",
        active_nav="",
        meta_title="مجله زاد | راهنمای گل، هدیه و مناسبت‌ها",
        meta_description="مطالب و راهنماهای زاد درباره گل، هدیه، نگهداری محصولات و برنامه‌ریزی مناسبت‌ها.",
        breadcrumbs=breadcrumbs,
        content_page="blog",
        suppress_default_hero=not db_hero,
    )

    if db_hero:
        context.update(db_hero)

    context["posts"] = posts

    return render(request, "blog_list.html", context)


def blog_detail(request, slug):
    post = get_object_or_404(
        NewsPost,
        slug=slug,
        status=PublishStatus.PUBLISHED,
    )

    recommended_items = list(
        _published_products()
        .select_related("category")
        .prefetch_related("tags")
        .order_by("-featured", "sort_order", "-created_at")[:3]
    )

    flower_category = _active_categories_for_section(Category.Section.FLOWERS).first()

    recommended_subcategory = None

    if flower_category:
        recommended_subcategory = {
            "label": flower_category.name,
            "url": reverse("flower_subcategory", args=[flower_category.slug]),
        }

    breadcrumbs = _with_home(
        [
            {"name": "Journal", "url": reverse("blog")},
            {"name": post.title, "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="category",
        active_nav="",
        meta_title=f"{post.title} | مجله زاد",
        meta_description=post.excerpt or "مطالعه این مطلب از مجله زاد درباره گل، هدیه و مناسبت‌ها.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="blog-detail",
        og_type="article",
        social_image=post.cover_image if post.cover_image else None,
    )

    hero_data = _hero_from_key(
        "blog",
        title=post.title,
        text=post.excerpt or "Read a note from the zad Journal.",
        image=post.cover_image.url if post.cover_image else "main/img/hero-contact.webp",
    )

    db_hero = _get_site_hero("blog", post.slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)

    recommended_category = {"label": "Flowers", "url": reverse("flowers")}
    related_links = [recommended_category]

    if recommended_subcategory:
        related_links.append(recommended_subcategory)

    context.update(
        {
            "post": post,
            "recommended_category": recommended_category,
            "recommended_subcategory": recommended_subcategory,
            "recommended_items": recommended_items,
            "related_links": related_links,
            "related_products": recommended_items,
        }
    )
    context["structured_data_graph"].append(article_node(post))

    return render(request, "blog_detail.html", context)


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

def robots_txt(request):
    lines = [
        "# Search and answer-engine crawlers",
        "User-agent: Googlebot",
        "User-agent: Bingbot",
        "User-agent: OAI-SearchBot",
        "User-agent: ChatGPT-User",
        "User-agent: PerplexityBot",
        "User-agent: Claude-SearchBot",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /auth/",
        "Disallow: /search/",
        "Disallow: /lead-request/",
        "Disallow: /csp-report/",
        "",
        "# Model-training crawlers are handled separately from search crawlers",
        "User-agent: GPTBot",
        "User-agent: ClaudeBot",
        "User-agent: Google-Extended",
        "User-agent: CCBot",
        "Disallow: /",
        "",
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /auth/",
        "Disallow: /search/",
        "Disallow: /lead-request/",
        "Disallow: /csp-report/",
        f"Sitemap: {settings.ZAD_SITE_URL}{reverse('sitemap')}",
    ]

    response = HttpResponse(
        "\n".join(lines),
        content_type="text/plain; charset=utf-8",
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


INDEXNOW_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def indexnow_key(request, key):
    configured_key = settings.INDEXNOW_KEY
    if (
        request.method not in {"GET", "HEAD"}
        or not configured_key
        or not INDEXNOW_KEY_PATTERN.fullmatch(configured_key)
        or key != configured_key
    ):
        raise Http404("IndexNow key not found")

    response = HttpResponse(configured_key, content_type="text/plain; charset=utf-8")
    response.headers["Cache-Control"] = "public, max-age=86400"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@csrf_exempt
@require_POST
def csp_report(request):
    if len(request.body) > 64 * 1024:
        return HttpResponse(status=413)

    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)

    report = payload.get("csp-report", payload) if isinstance(payload, dict) else {}
    security_logger.warning(
        "CSP violation document=%s directive=%s blocked=%s",
        report.get("document-uri", ""),
        report.get("violated-directive", report.get("effective-directive", "")),
        report.get("blocked-uri", ""),
    )
    return HttpResponse(status=204)


def custom_404(request, exception):
    """Render the site's branded not-found page with the shared base layout."""
    context = {
        "meta_title": "صفحه پیدا نشد | ZAD",
        "meta_description": "صفحه مورد نظر پیدا نشد.",
        "robots_content": "noindex,nofollow",
        "page_type": "error-404",
        "is_home": True,
    }
    return render(request, "404.html", context, status=404)
