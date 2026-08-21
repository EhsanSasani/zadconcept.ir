import hashlib
import json
import re

from django.db import DatabaseError
from django.http import HttpResponse

from ..models import HeroFont, HomeHeroSlide, SiteHero


HERO_FONT_CSS_STACKS = {
    "estedad": '"EstedadLocal", "VazirmatnLocal", Tahoma, sans-serif',
    "vazirmatn": '"VazirmatnLocal", "EstedadLocal", Tahoma, sans-serif',
    "cormorant": '"CormorantGaramond", "EstedadLocal", serif',
    "jakarta": '"PlusJakartaSans", "EstedadLocal", sans-serif',
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
