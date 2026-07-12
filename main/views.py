import json
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import LeadRequestForm
from .models import (
    Category,
    Event,
    FLOWER_CATEGORY_SLUGS,
    FLOWER_OCCASION_TAG_SLUGS,
    Flower,
    HomeHeroSlide,
    NewsPost,
    PageContentBlock,
    Product,
    PublishStatus,
    SAME_DAY_TAG_SLUG,
    SiteHero,
    Tag,
    WorkshopPageContent,
)


# =========================
# Page content
# =========================

SECTION_CONTENT = {
    "flowers": {
        "title": "Flowers",
        "nav": "flowers",
        "lead_type": "flower",
        "meta_title": "Luxury Flowers in Mashhad | zad",
        "meta_description": "Fresh flowers, premium styling, and fast coordination in Mashhad.",
        "intro": "Premium zad flowers with careful styling and fast coordination in Mashhad.",
        "faq": [
            {
                "question": "Do you offer same-day flower delivery in Mashhad?",
                "answer": "Yes. Same-day coordination is available for many orders during working hours.",
            },
            {
                "question": "Can I check today’s availability before ordering?",
                "answer": "Yes. Call zad or message us on Telegram to check available pieces and similar options.",
            },
            {
                "question": "What should I choose for formal or sympathy occasions?",
                "answer": "Stands and formal arrangements can be coordinated based on the occasion and color palette.",
            },
            {
                "question": "Can I schedule an order for later?",
                "answer": "Yes. Orders can be coordinated for today, tomorrow, or a selected date.",
            },
        ],
    },
    "bakery": {
        "title": "Bakery",
        "nav": "bakery",
        "lead_type": "bakery",
        "meta_title": "Premium Bakery Orders in Mashhad | zad",
        "meta_description": "Premium zad bakery pieces for gifting, hosting, and daily coordination by phone or Telegram.",
        "intro": "zad bakery pieces are made for hosting, gifting, and warm daily details.",
        "faq": [
            {
                "question": "Can I order bakery pieces for today?",
                "answer": "In many cases, yes. Availability depends on the day’s capacity.",
            },
            {
                "question": "Can bakery items be sent with flowers?",
                "answer": "Yes. Flowers and bakery pieces can be coordinated for one delivery time.",
            },
            {
                "question": "How should I order larger quantities?",
                "answer": "For larger or corporate orders, use the request form or call directly.",
            },
            {
                "question": "How fast does zad respond?",
                "answer": "During working hours, the first response is usually quick.",
            },
        ],
    },
    "gifts": {
        "title": "Gifts",
        "nav": "gifts",
        "lead_type": "gift",
        "meta_title": "Curated Gifts & Concept Store | zad Mashhad",
        "meta_description": "Minimal curated gifts, concept pieces, and gift coordination in Mashhad.",
        "intro": "Curated zad gifts for thoughtful, minimal, and premium choices.",
        "faq": [],
    },
}


CATEGORY_CONTENT_OVERRIDES = {
    "hand-bouquet": {
        "label": "دسته گل",
        "meta_title": "دسته گل لوکس در مشهد | ZAD",
        "meta_description": "دسته گل‌های زاد برای هدیه، تولد، عاشقانه و لحظه‌های روزمره در مشهد.",
        "intro": "انتخابی نرم و روشن برای هدیه‌های روزمره و لحظه‌های خاص.",
        "image": "main/img/sub-bouquet.jpg",
        "hero_image": "main/img/hero-subcategory.jpg",
    },
    "box": {
        "label": "باکس گل",
        "meta_title": "باکس گل لوکس در مشهد | ZAD",
        "meta_description": "باکس گل‌های زاد با چیدمان مینیمال، مناسب هدیه و سفارش سریع در مشهد.",
        "intro": "هدیه‌ای مرتب، شیک و آماده برای ارسال.",
        "image": "main/img/sub-box.jpg",
        "hero_image": "main/img/hero-subcategory.jpg",
    },
    "bouquet": {
        "label": "بوکت",
        "meta_title": "بوکت گل خاص در مشهد | ZAD",
        "meta_description": "بوکت‌های طراحی‌شده زاد برای انتخاب‌های خاص‌تر و لوکس‌تر.",
        "intro": "چیدمانی طراحی‌شده‌تر برای وقتی که انتخاب باید خاص‌تر باشد.",
        "image": "main/img/sub-bouquet.jpg",
        "hero_image": "main/img/hero-subcategory.jpg",
    },
    "stand": {
        "label": "استند گل",
        "meta_title": "استند گل در مشهد | ZAD",
        "meta_description": "استندهای گل رسمی زاد برای مراسم، ترحیم، افتتاحیه و لحظه‌های تشریفاتی.",
        "intro": "برای موقعیت‌های رسمی، محترمانه و پررنگ‌تر.",
        "image": "main/img/sub-stand.jpg",
        "hero_image": "main/img/hero-subcategory.jpg",
        },

    "wedding": {
        "label": "دسته گل عروس",
        "meta_title": "دسته گل عروس در مشهد | ZAD",
        "meta_description": "دسته گل عروس زاد با چیدمان لطیف، مینیمال و هماهنگ با مراسم.",
        "intro": "دسته‌گلی لطیف برای یکی از مهم‌ترین لحظه‌ها.",
        "image": "main/img/sub-bridal-bouquet.jpg",
        "hero_image": "main/img/hero-subcategory.jpg",
    },
    "jarl": {
        "label": "جار گل",
        "meta_title": "جار گل در مشهد | ZAD",
        "meta_description": "جار گل‌های زاد برای دکور، هدیه‌های خاص و انتخاب‌های متفاوت.",
        "intro": "فرمی متفاوت و دکوراتیو برای انتخاب‌های خاص‌تر.",
        "image": "main/img/sub-box.jpg",
        "hero_image": "main/img/hero-subcategory.jpg",
    },
    "plants": {
        "label": "گیاه",
        "meta_title": "گیاه هدیه‌ای در مشهد | ZAD",
        "meta_description": "گیاه‌های انتخاب‌شده زاد برای هدیه، خانه و لحظه‌های آرام‌تر.",
        "intro": "انتخابی ماندگارتر برای خانه، میز کار و هدیه‌های آرام‌تر.",
        "image": "main/img/sub-plant.jpg",
        "hero_image": "main/img/hero-subcategory.jpg",
    },
    "basket": {
        "label": "سبد گل",
        "meta_title": "سبد گل در مشهد | ZAD",
        "meta_description": "سبد گل‌های زاد برای هدیه و مراسم.",
        "intro": "یک دسته‌بندی قدیمی که فعلاً فقط برای سازگاری نگه داشته شده است.",
        "image": "main/img/sub-plant.jpg",
        "hero_image": "main/img/hero-subcategory.jpg",
    },
    "birthday-cakes": {
        "label": "Birthday Cakes",
        "meta_title": "Birthday Cakes | ZAD",
        "meta_description": "ZAD birthday cakes for warm celebrations and soft moments.",
        "intro": "Soft cakes for warm birthday moments.",
        "image": "main/img/cat-bakery.jpg",
        "hero_image": "main/img/hero-subcategory.jpg",
    },
    "cookies": {
        "label": "Cookies",
        "meta_title": "Cookies | ZAD",
        "meta_description": "ZAD cookies for gifting, gatherings and sweet little details.",
        "intro": "Small sweet bites for gentle celebrations.",
        "image": "main/img/cat-bakery.jpg",
        "hero_image": "main/img/hero-subcategory.jpg",
    },
}

CATEGORY_SLUG_ALIASES = {
    "plant": "plants",
    "wreath": "stand",
    "wedding-decoration": "wedding",
}


PAGE_HERO_CONTENT = {
    "occasions": {
        "kicker": "ZAD OCCASIONS",
        "title": "Occasions by ZAD",
        "text": "انتخاب‌هایی برای تولد، عشق، تبریک، دلجویی و لحظه‌هایی که باید ماندگار شوند.",
        "image": "main/img/hero-occasions.jpg",
    },
    "flowers": {
        "kicker": "ZAD Flowers",
        "title": "Flowers by ZAD",
        "text": "انتخاب گل برای لحظه‌های خاص، سفارش‌های فوری و چیدمان‌های اختصاصی.",
        "image": "main/img/flowers-hero.jpg",
    },
    "bakery": {
        "kicker": "zad Bakery",
        "title": "Sweet Little Rituals",
        "text": "Small sweet pieces for warmer celebrations.",
        "image": "main/img/hero-bakery.jpg",
    },
    "gifts": {
        "kicker": "zad Gifts",
        "title": "Chosen With Care",
        "text": "Little gifts with warmth, softness and meaning.",
        "image": "main/img/hero-gifts.jpg",
    },
    "subcategory": {
        "kicker": "zad Collection",
        "title": "Curated Softly",
        "text": "A smaller selection for a more exact feeling.",
        "image": "main/img/hero-subcategory.jpg",
    },
    "item": {
        "kicker": "zad Item",
        "title": "",
        "text": "",
        "image": "main/img/hero-gifts.jpg",
    },
    "contact": {
        "kicker": "Contact zad",
        "title": "Let’s Arrange It",
        "text": "For availability, timing and order details.",
        "image": "main/img/hero-contact.jpg",
    },
    "events": {
        "kicker": "zad Events",
        "title": "Gathered With Feeling",
        "text": "Workshops, gatherings and soft zad experiences.",
        "image": "main/img/hero-events.jpg",
    },
    "blog": {
        "kicker": "zad Journal",
        "title": "Soft Notes",
        "text": "Small ideas for flowers, gifts and moments.",
        "image": "main/img/hero-contact.jpg",
    },
    "faq": {
        "kicker": "zad Help",
        "title": "Little Answers",
        "text": "Simple answers before you call or order.",
        "image": "main/img/hero-faq.jpg",
    },
    "mashhad": {
        "kicker": "zad Mashhad",
        "title": "Made for Mashhad",
        "text": "Fast coordination for special orders in Mashhad.",
        "image": "main/img/hero-mashhad.jpg",
    },
    "about": {
        "kicker": "zad Concept Store",
        "title": "The Story of zad",
        "text": "A closer look at the care behind the brand.",
        "image": "main/img/hero-about.jpg",
    },
}


HOME_FAQ = [
    {
        "question": "What can I order from zad?",
        "answer": "Flowers, bakery pieces, curated gifts, and event coordination are available through zad.",
    },
    {
        "question": "Do you offer same-day delivery in Mashhad?",
        "answer": "Yes. Many orders can be coordinated for same-day delivery depending on availability.",
    },
    {
        "question": "What is the fastest way to coordinate an order?",
        "answer": "Calling zad is the fastest path. Telegram is available as the second option.",
    },
    {
        "question": "How do I start an event order?",
        "answer": "Use the events page or the request form and share the date, location, and request type.",
    },
]


VISIT_FAQ = [
    {
        "question": "Should I coordinate before visiting?",
        "answer": "For special orders, it is better to call before visiting so the team can prepare faster.",
    },
    {
        "question": "What are zad’s opening hours?",
        "answer": "zad is available every day from 10:00 to 22:00 unless announced otherwise.",
    },
    {
        "question": "What can I do during an in-person visit?",
        "answer": "You can review samples, receive guidance, and coordinate pickup or delivery.",
    },
    {
        "question": "Can I choose flowers and gifts together?",
        "answer": "Yes. zad can suggest flower and gift combinations for the same occasion.",
    },
]


CONTACT_FAQ = [
    {
        "question": "How fast does zad respond?",
        "answer": "During working hours, the first response is usually quick.",
    },
    {
        "question": "How can I place an order?",
        "answer": "Call zad, message on Telegram, or submit the short request form.",
    },
    {
        "question": "What information is needed for urgent orders?",
        "answer": "Name, mobile number, request type, delivery window, and a short note are enough to start.",
    },
    {
        "question": "Do you deliver outside Mashhad?",
        "answer": "The current focus is Mashhad, but special requests can be reviewed case by case.",
    },
]


FAQ_PAGE_ITEMS = [
    *HOME_FAQ,
    *VISIT_FAQ,
    *CONTACT_FAQ,
]


# =========================
# Generic helpers
# =========================

def _jsonld(data):
    return json.dumps(data, ensure_ascii=False)


def _faq_jsonld(faq_items):
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
            }
            for item in faq_items
        ],
    }


def _breadcrumbs_jsonld(request, breadcrumbs):
    items = []

    for position, crumb in enumerate(breadcrumbs, start=1):
        crumb_url = crumb.get("url") or request.path
        items.append(
            {
                "@type": "ListItem",
                "position": position,
                "name": crumb["name"],
                "item": request.build_absolute_uri(crumb_url),
            }
        )

    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items,
    }


def _with_home(items):
    return [{"name": "Home", "url": reverse("index")}, *items]


def _telegram_href():
    return getattr(settings, "zad_TELEGRAM_URL", "https://t.me/Flowerhouse_pv")


def _item_telegram_href(request, product):
    return _telegram_href()


def _stock_to_schema(stock_status):
    if stock_status == Product.StockStatus.OUT_OF_STOCK:
        return "https://schema.org/OutOfStock"

    if stock_status == Product.StockStatus.PREORDER:
        return "https://schema.org/PreOrder"

    return "https://schema.org/InStock"


def _product_jsonld(request, product):
    offer = {
        "@type": "Offer",
        "priceCurrency": "IRR",
        "availability": _stock_to_schema(product.stock_status),
        "url": request.build_absolute_uri(product.get_absolute_url()),
    }

    if product.price:
        offer["price"] = str(int(product.price) * 10)

    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "brand": {"@type": "Brand", "name": "zad"},
        "offers": offer,
    }

    if getattr(product, "cover_image", None):
        schema["image"] = [request.build_absolute_uri(product.cover_image.url)]

    return schema


def _event_to_iso(dt):
    current_tz = timezone.get_current_timezone()

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, current_tz)
    else:
        dt = timezone.localtime(dt, current_tz)

    return dt.isoformat()


COLLECTION_LANDING_CONTENT = {
    Category.Section.FLOWERS: {
        "hero_eyebrow": "FLOWER COLLECTION",
        "hero_title": "گل‌های زاد",
        "hero_text": "گل‌هایی برای تمام لحظه‌های خاص زندگی شما",
        "hero_image": "main/img/flowers-hero.jpg",
        "fallback_image": "main/img/cat-flowers.jpg",
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
        "cta_image": "main/img/footer-floral.jpg",
        "cta_alt": "سفارش اختصاصی گل",
    },
    Category.Section.BAKERY: {
        "hero_eyebrow": "ZAD SWEET BAR",
        "hero_title": "سوییت بار زاد",
        "hero_text": "طعم‌های شیرین برای لحظه‌های گرم و به‌یادماندنی",
        "hero_image": "main/img/hero-bakery.jpg",
        "fallback_image": "main/img/cat-bakery.jpg",
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
        "cta_image": "main/img/hero-bakery.jpg",
        "cta_alt": "سفارش اختصاصی سوییت بار",
    },
    Category.Section.GIFTS: {
        "hero_eyebrow": "ZAD CONCEPT STORE",
        "hero_title": "کانسپت استور زاد",
        "hero_text": "هدیه‌هایی خاص برای آدم‌ها و لحظه‌های خاص زندگی شما",
        "hero_image": "main/img/hero-gifts-v2.webp",
        "fallback_image": "main/img/cat-gifts.jpg",
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


def _hero_defaults(meta_title, meta_description):
    return {
        "page_hero_kicker": "zad",
        "page_hero_title": meta_title,
        "page_hero_text": meta_description,
        "page_hero_image": "main/img/hero-2.jpg",
    }


def _hero_from_key(key, *, title=None, text=None, image=None):
    hero = PAGE_HERO_CONTENT.get(key, {})

    return {
        "page_hero_kicker": hero.get("kicker", "zad"),
        "page_hero_title": title or hero.get("title", "zad"),
        "page_hero_text": text or hero.get("text", "A thoughtful zad selection for flowers, gifts, and special orders"),
        "page_hero_image": image or hero.get("image", "main/img/hero-2.jpg"),
    }


def _get_active_home_hero_slides():
    slides = list(
        HomeHeroSlide.objects.filter(is_active=True).order_by("sort_order", "id")
    )

    if slides:
        return [
            {
                "title": slide.title,
                "kicker": slide.kicker,
                "description": slide.description,
                "image_url": slide.image.url,
                "mobile_image_url": (
                    slide.mobile_image.url if slide.mobile_image else ""
                ),
                "primary_button_text": slide.primary_button_text,
                "primary_button_url": slide.primary_button_url,
                "secondary_button_text": slide.secondary_button_text,
                "secondary_button_url": slide.secondary_button_url,
                "show_content": True,
            }
            for slide in slides
        ]

    return [
        {
            "title": "Flowers, Bakery & Gifts in Mashhad",
            "kicker": "zad Concept Store",
            "description": "Premium flowers, bakery, and gifts with fast coordination in Mashhad.",
            "image_url": settings.STATIC_URL + "main/img/hero-1.jpg",
            "mobile_image_url": settings.STATIC_URL + "main/img/hero-mobile-1.jpg",
            "primary_button_text": "Call Now",
            "primary_button_url": "",
            "secondary_button_text": "تلگرام",
            "secondary_button_url": "",
            "show_content": False,
        },
        {
            "title": "Styled Details for Special Moments",
            "kicker": "Minimal & Premium",
            "description": "A polished zad experience across flowers, bakery, and gifts.",
            "image_url": settings.STATIC_URL + "main/img/hero-2.jpg",
            "mobile_image_url": settings.STATIC_URL + "main/img/hero-mobile-2.jpg",
            "primary_button_text": "",
            "primary_button_url": "",
            "secondary_button_text": "",
            "secondary_button_url": "",
            "show_content": False,
        },
        {
            "title": "Fast Coordination in Mashhad",
            "kicker": "zad Mashhad",
            "description": "Quick coordination for urgent orders and daily selections.",
            "image_url": settings.STATIC_URL + "main/img/hero-3.jpg",
            "mobile_image_url": settings.STATIC_URL + "main/img/hero-mobile-3.jpg",
            "primary_button_text": "",
            "primary_button_url": "",
            "secondary_button_text": "",
            "secondary_button_url": "",
            "show_content": False,
        },
    ]


def _site_hero_payload(hero):
    return {
        "kicker": hero.kicker or "zad",
        "title": hero.title,
        "text": hero.description,
        "image": hero.image.url if hero.image else "main/img/hero-2.jpg",
        "mobile_image": hero.mobile_image.url if hero.mobile_image else "",
    }


def _get_site_hero_slides(target_page, target_slug="", *, allow_fallback=True):
    heroes = list(
        SiteHero.objects.filter(
            is_active=True,
            target_page=target_page,
            target_slug=target_slug,
        )
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
        "page_hero_kicker": first["kicker"],
        "page_hero_title": first["title"],
        "page_hero_text": first["text"],
        "page_hero_image": first["image"],
        "page_hero_mobile_image": first["mobile_image"],
        "page_hero_slides": slides,
    }


def _default_context(
    request,
    *,
    page_type,
    active_nav,
    meta_title,
    meta_description,
    breadcrumbs=None,
    faq_items=None,
    item_id=None,
    enable_product_modal=False,
    content_page=None,
):
    context = {
        "page_type": page_type,
        "active_nav": active_nav,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "canonical_url": request.build_absolute_uri(request.path),
        "item_id": item_id,
        "extra_jsonld": [],
        "is_homepage": False,
        "enable_product_modal": enable_product_modal,
        "flowers_url": reverse("flowers"),
        "page_content": {
            block.section_key: block
            for block in PageContentBlock.objects.filter(
                page=content_page or page_type,
                is_active=True,
            ).order_by("sort_order", "section_key")
        },
        **_hero_defaults(meta_title, meta_description),
    }

    if breadcrumbs:
        context["breadcrumbs"] = breadcrumbs
        context["breadcrumbs_jsonld"] = _jsonld(
            _breadcrumbs_jsonld(request, breadcrumbs)
        )

    if faq_items:
        context["faq_items"] = faq_items
        context["faq_jsonld"] = _jsonld(_faq_jsonld(faq_items))

    return context


# =========================
# Product / category helpers
# =========================

def _published_products():
    return Product.objects.filter(
        is_active=True,
        publish_status=Product.PublishStatus.PUBLISHED,
        category__is_active=True,
    )


def _published_products_for_section(section):
    return (
        _published_products()
        .filter(category__section=section)
        .select_related("category")
        .prefetch_related("tags")
    )


def _active_categories_for_section(section):
    queryset = Category.objects.filter(
        section=section,
        is_active=True,
    )

    if section == Category.Section.FLOWERS:
        queryset = queryset.exclude(slug="wedding")

    return queryset.order_by("sort_order", "name")


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


def _category_content(category):
    override = CATEGORY_CONTENT_OVERRIDES.get(category.slug, {})

    return {
        "label": override.get("label") or category.name,
        "meta_title": override.get("meta_title") or f"{category.name} | zad",
        "meta_description": (
            override.get("meta_description")
            or category.description
            or f"Explore {category.name} products at zad."
        ),
        "intro": override.get("intro") or category.description or "A curated selection for this mood.",
        "image": override.get("image") or "main/img/sub-bouquet.jpg",
        "hero_image": override.get("hero_image") or "main/img/hero-subcategory.jpg",
    }


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

OCCASION_CARD_CONTENT = {
    "birthday": {
        "title": "تولد",
        "hero_title": "گل تولد",
        "intro": "برای شادی‌های روشن.",
        "hero_text": "برای لحظه‌ای که باید با گل، رنگ و یک یاد شیرین ماندگار شود.",
        "image": "main/img/occasions/birthday.jpg",
    },
    "romantic": {
        "title": "عاشقانه",
        "hero_title": "گل عاشقانه",
        "intro": "برای لحظه‌های نزدیک.",
        "hero_text": "برای گفتن دوستت دارم؛ آرام‌تر و زیباتر از هر کلمه.",
        "image": "main/img/occasions/romantic.jpg",
    },
    "congratulation": {
        "title": "تبریک",
        "hero_title": "گل تبریک",
        "intro": "برای خبرهای خوب.",
        "hero_text": "برای جشن گرفتن خبرهای خوب و شروع‌های روشن.",
        "image": "main/img/occasions/special.jpg",
    },
    "apology": {
        "title": "معذرت‌خواهی",
        "hero_title": "گل معذرت‌خواهی",
        "intro": "برای دلجویی آرام.",
        "hero_text": "برای وقتی که یک انتخاب صمیمی، آغاز دوباره‌ی گفت‌وگوست.",
        "image": "main/img/occasions/special.jpg",
    },
    "condolence": {
        "title": "ترحیم",
        "hero_title": "گل ترحیم",
        "intro": "برای همراهی محترمانه.",
        "hero_text": "برای ابراز همدلی؛ باوقار، آرام و محترمانه.",
        "image": "main/img/occasions/condolence.jpg",
    },
    "proposal": {
        "title": "خواستگاری",
        "hero_title": "گل خواستگاری",
        "intro": "برای شروعی رسمی.",
        "hero_text": "برای شروعی به‌یادماندنی، با جزئیاتی ظریف و باشکوه.",
        "image": "main/img/occasions/special.jpg",
    },
    "engagement": {
        "title": "بله‌برون",
        "hero_title": "گل بله‌برون",
        "intro": "برای پیمان‌های شیرین.",
        "hero_text": "برای جشنی صمیمی و شیرین در آغاز یک همراهی.",
        "image": "main/img/occasions/special.jpg",
    },
    "no-occasion": {
        "title": "بدون مناسبت",
        "hero_title": "گل بدون مناسبت",
        "intro": "برای بی‌دلیل دوست داشتن.",
        "hero_text": "برای همان روزهای معمولی که با یک یاد کوچک، خاص می‌شوند.",
        "image": "main/img/occasions/special.jpg",
    },
    "wedding": {
        "title": "عروسی",
        "hero_title": "گل عروسی",
        "intro": "برای روزهای سپید.",
        "hero_text": "برای روزی سپید، لطیف و به‌یادماندنی.",
        "image": "main/img/occasions/special.jpg",
    },
}
OCCASION_EN_LABELS = {
    "birthday": "Birthday",
    "romantic": "Romantic",
    "congratulation": "Congratulations",
    "apology": "Apology",
    "condolence": "Sympathy",
    "proposal": "Proposal",
    "engagement": "Engagement",
    "no-occasion": "Just Because",
    "wedding": "Wedding",
}

OCCASION_DETAIL_HERO_IMAGE = "main/img/occasion-detail-hero-v1.webp"
OCCASION_DETAIL_HERO_MOBILE_IMAGE = "main/img/occasion-detail-hero-mobile-v1.webp"


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
                "main/img/occasions/special.jpg",
            )
        ),
        "intro": tag.description
        or content.get(
            "intro",
            "Curated ideas for this occasion.",
        ),
    }


def _active_occasion_tags(limit=None):
    queryset = Tag.objects.filter(
        is_occasion=True,
        is_active=True,
    ).order_by("sort_order", "name")

    if limit:
        queryset = queryset[:limit]

    return list(queryset)


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
            "label": "All",
            "url": base_url,
            "is_active": not selected_slug,
        }
    ]

    for category in categories:
        url = f"{base_url}?category={category.slug}"

        if include_section:
            url += f"&section={category.section}"

        links.append(
            {
                "label": category.name,
                "url": url,
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
        for category in Category.objects.filter(
            section=Category.Section.FLOWERS,
            is_active=True,
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
        meta_title="zad | Flowers, Bakery & Gifts in Mashhad",
        meta_description="zad Concept Store in Mashhad for flowers, bakery, gifts, events, and fast coordination.",
        faq_items=HOME_FAQ,
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
        Q(tags__slug=SAME_DAY_TAG_SLUG) | Q(tags__slug="same-day") | Q(tags__name="ارسال روز") | Q(tags__name="ارسال فوری"),
        category__section=Category.Section.FLOWERS,
    )
    .select_related("category")
    .prefetch_related("tags")
    .distinct()
    .order_by("sort_order", "-created_at")[:12]
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
        faq_items=config["faq"] or None,
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
    "apology",
    "condolence",
    "proposal",
    "engagement",
    "wedding",
    "no-occasion",
]

SAME_DAY_TAG_SLUGS = [
    "same-day",
    "same-day",
]


FLOWER_TYPE_FALLBACK_IMAGES = {
    "hand-bouquet": "main/img/sub-bouquet.jpg",
    "box": "main/img/sub-box.jpg",
    "bouquet": "main/img/sub-bouquet.jpg",
    "stand": "main/img/sub-stand.jpg",
    "jarl": "main/img/sub-plant.jpg",
    "plants": "main/img/sub-plant.jpg",
    "wedding": "main/img/sub-bridal-bouquet.jpg",
}



OCCASION_FALLBACK_IMAGES = {
    "birthday": "main/img/occasions/birthday.jpg",
    "romantic": "main/img/occasions/romantic.jpg",
    "congratulation": "main/img/occasions/special.jpg",
    "apology": "main/img/occasions/special.jpg",
    "condolence": "main/img/occasions/condolence.jpg",
    "proposal": "main/img/occasions/special.jpg",
    "engagement": "main/img/occasions/special.jpg",
    "wedding": "main/img/occasions/special.jpg",
    "no-occasion": "main/img/occasions/special.jpg",
}



def _sort_by_slug_order(items, slug_order):
    order_map = {slug: index for index, slug in enumerate(slug_order)}
    return sorted(items, key=lambda item: order_map.get(item.slug, 999))




def _flower_occasion_cards():
    tags = list(
        Tag.objects.filter(
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
                    else OCCASION_FALLBACK_IMAGES.get(tag.slug, "main/img/occasions/special.jpg")
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

    products = list(queryset[:limit])

    if products:
        return products

    return list(
        _published_products_for_section(Category.Section.FLOWERS)
        .order_by("-featured", "sort_order", "-created_at")[:limit]
    )


FLOWER_FILTER_ORDER = [
    "hand-bouquet",
    "box",
    "bouquet",
    "jarl",
    "stand",
    "plants",
]


def _collection_landing_page(request, section, *, excluded_category_slugs=()):
    config = SECTION_CONTENT[section]
    landing = COLLECTION_LANDING_CONTENT[section]

    products_qs = _published_products_for_section(section)
    categories_qs = Category.objects.filter(section=section, is_active=True)

    if excluded_category_slugs:
        products_qs = products_qs.exclude(category__slug__in=excluded_category_slugs)
        categories_qs = categories_qs.exclude(slug__in=excluded_category_slugs)

    selected_category_slug = request.GET.get("category") or ""
    selected_category = None

    if selected_category_slug:
        selected_category = get_object_or_404(
            categories_qs,
            slug=selected_category_slug,
        )
        products_qs = products_qs.filter(category=selected_category)

    products_qs = _catalog_ordered_products(products_qs, section)
    page_obj = _paginate_products(request, products_qs)
    products = list(page_obj.object_list)

    if request.GET.get("partial") == "products":
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

        return JsonResponse(
            {
                "html": html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )

    categories = list(categories_qs.distinct().order_by("sort_order", "name"))
    if section == Category.Section.FLOWERS:
        order = {slug: index for index, slug in enumerate(FLOWER_FILTER_ORDER)}
        categories.sort(key=lambda category: order.get(category.slug, len(order)))

    filter_categories = [
        {
            "name": category.name,
            "slug": category.slug,
            "url": _section_category_url(category),
        }
        for category in categories
    ]

    context = _default_context(
        request,
        page_type="flowers_landing",
        active_nav=config["nav"],
        meta_title=config["meta_title"],
        meta_description=config["meta_description"],
        breadcrumbs=None,
        faq_items=config.get("faq") or None,
        enable_product_modal=True,
        content_page=section,
    )
    page_hero = _get_site_hero(section)
    context.update(page_hero or _hero_from_key(section))
    context.update(
        {
            "section": section,
            "catalog_products": products,
            "catalog_page_obj": page_obj,
            "catalog_filter_categories": filter_categories,
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
        excluded_category_slugs=("wedding",),
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

    categories = list(_active_categories_for_section(section))

    if section == Category.Section.FLOWERS:
        products_qs = products_qs.exclude(category__slug="wedding")

    selected_category = None
    selected_slug = request.GET.get("category") or ""

    if selected_slug:
        if section == Category.Section.FLOWERS and selected_slug == "wedding":
            return redirect("occasion_detail", slug="wedding", permanent=True)

        selected_category = get_object_or_404(
            Category,
            section=section,
            slug=selected_slug,
            is_active=True,
        )
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
        meta_title=f"{title} | zad",
        meta_description=f"View all {config['title']} products at zad.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="subcategory",
    )

    hero_data = _hero_from_key(
        section,
        title=title,
        text="Explore all active products in this section.",
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
            "related_posts": [],
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "subcategory.html", context)

def flowers_same_day(request):
    products = (
        Product.objects.filter(
            category__section=Category.Section.FLOWERS,
            is_active=True,
            publish_status=Product.PublishStatus.PUBLISHED,
            tags__slug__in=SAME_DAY_TAG_SLUGS,
        )
        .select_related("category")
        .prefetch_related("tags")
        .distinct()
        .order_by("sort_order", "-updated_at")
    )

    context = {
        "page_type": "catalog",
        "active_nav": "flowers",
        "page_hero_title": "ارسال امروز",
        "page_hero_text": "گل‌های آماده برای ارسال سریع در شهر مشهد.",
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

    return render(request, "subcategory.html", context)

def flowers_all(request):
    return _section_all_products(request, Category.Section.FLOWERS)


def bakery_all(request):
    return _section_all_products(request, Category.Section.BAKERY)


def gifts_all(request):
    return _section_all_products(request, Category.Section.GIFTS)





def _section_subcategory(request, section, subcategory_slug):
    category = get_object_or_404(
        Category,
        section=section,
        slug=subcategory_slug,
        is_active=True,
    )

    config = SECTION_CONTENT[section]
    content = _category_content(category)

    items = list(
        _published_products()
        .filter(category=category)
        .select_related("category")
        .prefetch_related("tags")
        .order_by("-featured", "sort_order", "-created_at")[:48]
    )

    related_posts = list(
        NewsPost.objects.filter(status=PublishStatus.PUBLISHED).order_by(
            "-published_at",
            "-created_at",
        )[:3]
    )

    breadcrumbs = _with_home(
        [
            {"name": config["title"], "url": reverse(section)},
            {"name": category.name, "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="subcategory",
        active_nav=config["nav"],
        meta_title=content["meta_title"],
        meta_description=content["meta_description"],
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="subcategory",
    )

    hero_data = _hero_from_key(
        "subcategory",
        title=content["label"],
        text=content["intro"],
        image=category.cover_image.url if category.cover_image else content["hero_image"],
    )

    db_hero = _get_site_hero("subcategory", category.slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "subcategory_slug": category.slug,
            "subcategory_label": category.name,
            "collection_title": category.name,
            "collection_intro": content["intro"],
            "items": items,
            "related_posts": related_posts if section == Category.Section.FLOWERS else [],
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "subcategory.html", context)


def flower_subcategory(request, subcategory_slug):
    canonical_slug = CATEGORY_SLUG_ALIASES.get(subcategory_slug, subcategory_slug)

    if canonical_slug == "wedding":
        return redirect("occasion_detail", slug="wedding", permanent=True)

    if canonical_slug != subcategory_slug:
        return redirect("flower_subcategory", subcategory_slug=canonical_slug)

    return _section_subcategory(request, Category.Section.FLOWERS, canonical_slug)


def bakery_subcategory(request, subcategory_slug):
    return _section_subcategory(request, Category.Section.BAKERY, subcategory_slug)


def gift_subcategory(request, subcategory_slug):
    return _section_subcategory(request, Category.Section.GIFTS, subcategory_slug)


def flower_occasion(request, slug):
    occasion = get_object_or_404(
        Tag,
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
        Category.objects.filter(
            pk__in=available_category_ids,
            is_active=True,
        ).order_by("sort_order", "name")
    )

    selected_slug = request.GET.get("category") or ""
    selected_category = None
    products_qs = base_products_qs

    if selected_slug:
        selected_category = get_object_or_404(
            Category,
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
        meta_title=f"{title} | zad",
        meta_description=f"View {title} at zad with fast order coordination.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="occasion-detail",
    )

    hero_data = _occasion_detail_hero(occasion, title=title)

    db_hero = _get_site_hero("occasions", occasion.slug, allow_fallback=False)

    if db_hero:
        hero_data.update(db_hero)

    # Occasion detail pages always share the same responsive art direction.
    # Tag-specific CMS copy can still override the fallback title and text.
    hero_data.update(
        {
            "page_hero_image": OCCASION_DETAIL_HERO_IMAGE,
            "page_hero_mobile_image": OCCASION_DETAIL_HERO_MOBILE_IMAGE,
        }
    )
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
    active_nav = section if section in SECTION_CONTENT else ""

    subcategory_url = None
    subcategory_label = None

    if category and category.section in SECTION_CATEGORY_ROUTE_NAMES:
        subcategory_url = _section_category_url(category)
        subcategory_label = category.name

    breadcrumbs = [{"name": "Home", "url": reverse("index")}]

    if section and section in SECTION_CONTENT:
        breadcrumbs.append(
            {
                "name": SECTION_CONTENT[section]["title"],
                "url": reverse(section),
            }
        )

    if subcategory_url and subcategory_label:
        breadcrumbs.append(
            {
                "name": subcategory_label,
                "url": subcategory_url,
            }
        )

    breadcrumbs.append({"name": product.name, "url": None})

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
            .order_by("-featured", "sort_order", "-created_at")[: 6 - len(similar_items)]
        )
        similar_items.extend(extra_items)

    description = (
        product.description[:140]
        if product.description
        else "Call zad for availability, delivery timing, and order coordination."
    )

    context = _default_context(
        request,
        page_type="item",
        active_nav=active_nav,
        meta_title=f"{product.name} | zad",
        meta_description=f"View {product.name} at zad. Call for availability, delivery timing, and order coordination.",
        breadcrumbs=breadcrumbs,
        item_id=product.pk,
        enable_product_modal=True,
        content_page="product",
    )

    hero_data = _hero_from_key(
        "item",
        title=product.name,
        text=description,
        image=product.cover_image.url if getattr(product, "cover_image", None) else "main/img/hero-gifts.jpg",
    )

    db_hero = _get_site_hero("item", product.slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "product": product,
            "category_name": category_name,
            "section_label": SECTION_CONTENT[section]["nav"].title() if section in SECTION_CONTENT else "Collection",
            "category_url": reverse(section) if section in SECTION_CONTENT else reverse("index"),
            "subcategory_url": subcategory_url,
            "subcategory_label": subcategory_label,
            "similar_items": similar_items,
            "item_telegram_href": _item_telegram_href(request, product),
            "item_call_text": "تماس",
            "item_telegram_text": "تلگرام",
            "mashhad_order_url": reverse("mashhad_flower_order"),
        }
    )

    context["extra_jsonld"].append(_jsonld(_product_jsonld(request, product)))

    return context


def product_detail(request, pk: int, slug: str):
    product = get_object_or_404(
        _published_products().select_related("category").prefetch_related("tags", "gallery_images"),
        pk=pk,
    )

    return redirect(product.get_absolute_url(), permanent=True)


def _section_product_detail(request, section, category_slug, slug):
    product = get_object_or_404(
        _published_products()
        .filter(category__section=section)
        .select_related("category")
        .prefetch_related("tags", "gallery_images"),
        slug=slug,
    )

    if product.category.slug != category_slug:
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
        Flower.objects.filter(
            is_active=True,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        .select_related("category")
        .prefetch_related("tags", "gallery_images"),
        pk=pk,
    )

    return redirect(flower.get_absolute_url(), permanent=True)


def flower_detail_redirect(request, pk: int):
    flower = get_object_or_404(
        Flower.objects.filter(
            is_active=True,
            publish_status=Product.PublishStatus.PUBLISHED,
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
        meta_title="Occasions | zad",
        meta_description="Explore zad flowers, bakery, and gifts by occasion.",
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
    occasion = get_object_or_404(
        Tag,
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
        .order_by("category__section", "-featured", "sort_order", "-created_at")
    )

    available_category_ids = list(
        base_products_qs.values_list("category_id", flat=True).distinct()
    )
    available_categories = list(
        Category.objects.filter(
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

        selected_category = get_object_or_404(Category, **category_lookup)
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
        meta_title=f"{occasion.name} | zad",
        meta_description=f"zad suggestions for {occasion.name}.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
    )

    hero_data = _occasion_detail_hero(occasion)
    db_hero = _get_site_hero("occasions", occasion.slug, allow_fallback=False)

    if db_hero:
        hero_data.update(db_hero)

    # Keep the visual fixed across every occasion tag while allowing each tag
    # (or its CMS hero record) to provide its own title and description.
    hero_data.update(
        {
            "page_hero_image": OCCASION_DETAIL_HERO_IMAGE,
            "page_hero_mobile_image": OCCASION_DETAIL_HERO_MOBILE_IMAGE,
        }
    )
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
        meta_title="ورکشاپ‌های زاد",
        meta_description="ورکشاپ‌های گل‌آرایی زاد؛ تجربه‌ای آرام، زیبا و الهام‌بخش.",
        breadcrumbs=breadcrumbs,
    )

    page_hero = _get_site_hero("events")
    workshop_copy = WorkshopPageContent.current() or WorkshopPageContent()

    if page_hero:
        context.update(page_hero)

    context.update(
        {
            "workshops_hero_kicker": (
                page_hero["page_hero_kicker"] if page_hero else "ZAD WORKSHOPS"
            ),
            "workshops_hero_title": (
                page_hero["page_hero_title"]
                if page_hero
                else "ورکشاپ‌های گل‌آرایی زاد"
            ),
            "workshops_hero_text": (
                page_hero["page_hero_text"]
                if page_hero
                else "تجربه‌ای آرام، زیبا و الهام‌بخش برای ساختن لحظه‌هایی که در ذهن می‌مانند."
            ),
            "workshops_hero_image": (
                page_hero["page_hero_image"]
                if page_hero
                else "main/img/workshops-hero.jpg"
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
        meta_title=f"{event.title} | zad Events",
        meta_description=f"Details for {event.title} at zad: time, location, and visit coordination.",
        breadcrumbs=breadcrumbs,
        content_page="event-detail",
    )

    hero_data = _hero_from_key(
        "events",
        title=event.title,
        text=event.description,
        image=event.cover_image.url if event.cover_image else "main/img/hero-events.jpg",
    )

    db_hero = _get_site_hero("events", event.slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)

    event_schema = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": event.title,
        "description": event.description,
        "startDate": _event_to_iso(event.start_at),
        "endDate": _event_to_iso(event.end_at),
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {
            "@type": "Place",
            "name": "zad",
            "address": event.location,
        },
        "organizer": {
            "@type": "Organization",
            "name": "zad",
            "url": getattr(settings, "zad_SITE_URL", "https://zad.ir"),
        },
        "url": request.build_absolute_uri(event.get_absolute_url()),
    }

    if event.cover_image:
        event_schema["image"] = [request.build_absolute_uri(event.cover_image.url)]

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

    context["extra_jsonld"].append(_jsonld(event_schema))

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

    context = _default_context(
        request,
        page_type="local",
        active_nav="mashhad",
        meta_title="Mashhad Orders | zad",
        meta_description="zad Mashhad order hub for flowers, same-day delivery, and fast coordination.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="mashhad",
    )

    hero_data = _hero_from_key("mashhad")
    db_hero = _get_site_hero("mashhad")

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
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
        title = "Flower Orders in Mashhad"
        subtitle = "Premium flower selection with fast, clear coordination."
        meta_title = "Flower Orders in Mashhad | zad"
        meta_description = "Flower orders in Mashhad with quick response, premium styling, and phone coordination."
    elif landing_type == "delivery":
        title = "Same-day Flower Delivery"
        subtitle = "Same-day delivery with zad packaging standards."
        meta_title = "Same-day Flower Delivery in Mashhad | zad"
        meta_description = "Same-day flower delivery in Mashhad with phone support and curated daily options."
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
            "question": "Which Mashhad areas are covered for urgent orders?",
            "answer": "Most central and high-demand areas are covered during working hours.",
        },
        {
            "question": "How early should I coordinate?",
            "answer": "For same-day delivery, it is better to coordinate at least 2–3 hours ahead.",
        },
        {
            "question": "Can I see the final item before delivery?",
            "answer": "When requested, the final image can be coordinated before dispatch.",
        },
        {
            "question": "What happens if my selected item is unavailable?",
            "answer": "Similar options with the same quality level will be suggested before delivery.",
        },
        {
            "question": "Can I coordinate quickly by phone?",
            "answer": "Yes. The call button is available across the site for direct coordination.",
        },
        {
            "question": "What do you need for an occasion order?",
            "answer": "Occasion type, delivery time, approximate budget, and address are enough to start.",
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
        faq_items=local_faq,
        enable_product_modal=True,
        content_page="mashhad",
    )

    hero_data = _hero_from_key("mashhad", title=title, text=subtitle)
    db_hero = _get_site_hero("mashhad")

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
                "Premium, minimal styling for the occasion",
                "Fast response and clear coordination before delivery",
                "Same-day delivery in key Mashhad areas",
                "Professional, gift-ready packaging",
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
        meta_title="Contact zad | Order Coordination",
        meta_description="Contact zad for ordering, guidance, availability, and delivery timing.",
        breadcrumbs=breadcrumbs,
        faq_items=CONTACT_FAQ,
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
        meta_title="FAQ | zad",
        meta_description="Common questions about zad orders, delivery, opening hours, and event coordination.",
        breadcrumbs=breadcrumbs,
        faq_items=FAQ_PAGE_ITEMS,
        content_page="faq",
    )

    hero_data = _hero_from_key("faq")
    db_hero = _get_site_hero("faq")

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context["faq_page_items"] = FAQ_PAGE_ITEMS

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
# Blog
# =========================

def blog(request):
    posts = list(
        NewsPost.objects.filter(
            status=PublishStatus.PUBLISHED,
        ).order_by("-published_at", "-created_at")
    )

    breadcrumbs = _with_home([{"name": "Journal", "url": None}])

    context = _default_context(
        request,
        page_type="category",
        active_nav="",
        meta_title="zad Journal | Ideas & Guides",
        meta_description="zad journal notes about flowers, gifts, and occasion planning.",
        breadcrumbs=breadcrumbs,
        content_page="blog",
    )

    hero_data = _hero_from_key("blog")
    db_hero = _get_site_hero("blog")

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
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
        meta_title=f"{post.title} | zad Journal",
        meta_description=post.excerpt or "Read a note from the zad Journal.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="blog-detail",
    )

    hero_data = _hero_from_key(
        "blog",
        title=post.title,
        text=post.excerpt or "Read a note from the zad Journal.",
        image=post.cover_image.url if post.cover_image else "main/img/hero-contact.jpg",
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

    return render(request, "blog_detail.html", context)


# =========================
# Leads
# =========================

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

    if form.is_valid():
        lead = form.save(commit=False)
        lead.source_page = request.POST.get("source_page", "")
        lead.save()
        messages.success(request, "Your request has been submitted. zad will contact you soon.")
    else:
        messages.error(request, "Please complete the form correctly and try again.")

    return redirect(next_url)


# =========================
# SEO
# =========================

def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /auth/",
        "Disallow: /search/",
        f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}",
    ]

    return HttpResponse(
        "\n".join(lines),
        content_type="text/plain; charset=utf-8",
    )


def custom_404(request, exception):
    """Render the site's branded not-found page with the shared base layout."""
    context = {
        "meta_title": "صفحه پیدا نشد | ZAD",
        "meta_description": "صفحه مورد نظر پیدا نشد.",
        "page_type": "error-404",
        "is_home": True,
    }
    return render(request, "404.html", context, status=404)
