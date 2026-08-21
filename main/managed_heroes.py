from django.conf import settings

from .models import HomeHeroSlide, SiteHero
from .page_presentation import _public_brand_copy


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
