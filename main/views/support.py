"""Shared view support pending extraction into content and hero layers."""

import hashlib
import json
import re
from datetime import timedelta

from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import DatabaseError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from ..content.catalog import (
    CATALOG_PAGE_SIZE,
    CATEGORY_CONTENT_OVERRIDES,
    CATEGORY_SLUG_ALIASES,
    COLLECTION_LANDING_CONTENT,
    HERO_FONT_CSS_STACKS,
    HERO_POSITION_VALUES,
    OCCASION_CARD_CONTENT,
    OCCASION_DETAIL_HERO_IMAGE,
    OCCASION_DETAIL_HERO_MOBILE_IMAGE,
    OCCASION_EN_LABELS,
    PAGE_HERO_CONTENT,
    SECTION_ALL_ROUTE_NAMES,
    SECTION_CATEGORY_ROUTE_NAMES,
    SECTION_CONTENT,
)
from ..models import (
    Category,
    Event,
    FLOWER_OCCASION_TAG_SLUGS,
    HeroFont,
    HomeHeroSlide,
    NewsPost,
    PageContentBlock,
    PublishStatus,
    SiteHero,
    Tag,
    WorkshopPageContent,
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
from ..presenters.catalog import category_filter_links
from ..selectors.catalog import active_occasion_tags

LEGACY_FLOWER_BRAND_PHRASES = (
    "گل‌های زاد",
    "گل های زاد",
    "گل‌ های زاد",
    "گل‌ های‌ زاد",
    "گلهای زاد",
)
FLOWER_STUDIO_NAME = "استودیو گل زاد"


def _public_brand_copy(value):
    """Normalize legacy public-facing flower brand copy at render time."""

    if not isinstance(value, str):
        return value

    for phrase in LEGACY_FLOWER_BRAND_PHRASES:
        value = value.replace(phrase, FLOWER_STUDIO_NAME)

    return value


# =========================
# Page content
# =========================








def _with_home(items):
    return [{"name": "Home", "url": reverse("index")}, *items]


def _telegram_href():
    return getattr(settings, "zad_TELEGRAM_URL", "https://t.me/Flowerhouse_pv")


def _item_telegram_href(request, product):
    return _telegram_href()




def _hero_defaults(meta_title, meta_description):
    return {
        "page_hero_kicker": "zad",
        "page_hero_title": meta_title,
        "page_hero_text": meta_description,
        "page_hero_image": "main/img/hero-2.webp",
        "page_hero_style_class": "",
        "page_hero_content_position": "center-left",
        "page_hero_mobile_content_position": "bottom-center",
    }


def _hero_from_key(key, *, title=None, text=None, image=None):
    hero = PAGE_HERO_CONTENT.get(key, {})

    return {
        "page_hero_kicker": _public_brand_copy(hero.get("kicker", "zad")),
        "page_hero_title": _public_brand_copy(title or hero.get("title", "zad")),
        "page_hero_text": _public_brand_copy(
            text
            or hero.get(
                "text",
                "A thoughtful zad selection for flowers, gifts, and special orders",
            )
        ),
        "page_hero_image": image or hero.get("image", "main/img/hero-2.webp"),
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
                "show_content": True,
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
        "kicker": _public_brand_copy(hero.kicker or "zad"),
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
    page_content = {}
    if content_page:
        page_content = {
            block.section_key: {
                "kicker": _public_brand_copy(block.kicker),
                "title": _public_brand_copy(block.title),
                "body": _public_brand_copy(block.body),
                "cta_text": _public_brand_copy(block.cta_text),
                "cta_url": block.cta_url,
            }
            for block in PageContentBlock.objects.filter(
                page=content_page,
                is_active=True,
            ).order_by("sort_order", "section_key")
        }
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
        "enable_product_modal": enable_product_modal,
        "html_lang": html_lang,
        "html_dir": html_dir,
        "alternate_links": alternate_links or [],
        "hide_global_chrome": hide_global_chrome,
        "suppress_default_hero": suppress_default_hero,
        "has_managed_site_hero": False,
        "page_content": page_content,
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


def _category_content(category):
    override = CATEGORY_CONTENT_OVERRIDES.get(category.slug, {})

    return {
        "label": override.get("label") or category.name,
        "meta_title": override.get("meta_title") or f"{category.name} در مشهد | زاد",
        "meta_description": (
            override.get("meta_description")
            or category.description
            or f"مشاهده و سفارش محصولات {category.name} زاد با هماهنگی ارسال در مشهد."
        ),
        "intro": (
            override.get("intro")
            or category.description
            or "انتخابی از محصولات این دسته برای لحظه‌های شما."
        ),
        "image": override.get("image") or "main/img/sub-bouquet.webp",
        "hero_image": override.get("hero_image") or "main/img/hero-subcategory.webp",
    }







def _occasion_detail_hero(occasion, *, title=None):
    content = OCCASION_CARD_CONTENT.get(occasion.slug, {})
    english_label = OCCASION_EN_LABELS.get(
        occasion.slug,
        occasion.slug.replace("-", " ").title(),
    )

    return {
        "page_hero_kicker": f"ZAD OCCASIONS · {english_label}",
        "page_hero_title": title or content.get("title") or occasion.name,
        "page_hero_text": (
            occasion.description
            or content.get("hero_text")
            or content.get("intro")
            or "انتخاب‌هایی هماهنگ برای این لحظه."
        ),
        "page_hero_image": OCCASION_DETAIL_HERO_IMAGE,
        "page_hero_mobile_image": OCCASION_DETAIL_HERO_MOBILE_IMAGE,
        "page_hero_style_class": "hero-style--occasion-detail",
        "page_hero_content_position": "center-right",
        "page_hero_mobile_content_position": "bottom-right",
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

    return {
        "slug": category.slug,
        "label": category.name,
        "url": _section_category_url(category),
        "image": category.cover_image.url if category.cover_image else content["image"],
        "intro": category.description or content["intro"],
        "has_children": category.has_active_children,
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
        for tag in active_occasion_tags(limit=limit)
    ]


def _filter_links_for_categories(
    base_url,
    categories,
    selected_slug=None,
    *,
    selected_section=None,
    include_section=False,
):
    return category_filter_links(
        base_url,
        categories,
        selected_slug,
        selected_section=selected_section,
        include_section=include_section,
        category_url=_section_category_url,
    )


# =========================
# Home
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
