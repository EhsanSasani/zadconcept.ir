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


SECTION_CONTENT = {
    "flowers": {
        "title": "Flowers",
        "nav": "flowers",
        "lead_type": "flower",
        "meta_title": "سفارش گل لوکس در مشهد | زاد",
        "meta_description": "سفارش گل تازه، چیدمان اختصاصی و هماهنگی سریع ارسال در مشهد با زاد.",
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
        "meta_title": "سفارش سوئیت‌بار و شیرینی در مشهد | زاد",
        "meta_description": "سفارش محصولات سوئیت‌بار زاد برای هدیه، پذیرایی و مناسبت‌ها در مشهد.",
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
        "meta_title": "هدیه و کانسپت استور در مشهد | زاد",
        "meta_description": "انتخاب و سفارش هدیه‌های خاص و مینیمال از کانسپت استور زاد در مشهد.",
        "intro": "Curated zad gifts for thoughtful, minimal, and premium choices.",
        "faq": [],
    },
}


PAGE_HERO_CONTENT = {
    "occasions": {
        "kicker": "ZAD OCCASIONS",
        "title": "Occasions by ZAD",
        "text": "انتخاب‌هایی برای تولد، عشق، تبریک، دلجویی و لحظه‌هایی که باید ماندگار شوند.",
        "image": "main/img/hero-occasions.webp",
    },
    "flowers": {
        "kicker": "ZAD Flowers",
        "title": "Flowers by ZAD",
        "text": "انتخاب گل برای لحظه‌های خاص، سفارش‌های فوری و چیدمان‌های اختصاصی.",
        "image": "main/img/flowers-hero.webp",
    },
    "bakery": {
        "kicker": "zad Bakery",
        "title": "Sweet Little Rituals",
        "text": "Small sweet pieces for warmer celebrations.",
        "image": "main/img/hero-bakery.webp",
    },
    "gifts": {
        "kicker": "zad Gifts",
        "title": "Chosen With Care",
        "text": "Little gifts with warmth, softness and meaning.",
        "image": "main/img/hero-gifts.webp",
    },
    "subcategory": {
        "kicker": "zad Collection",
        "title": "Curated Softly",
        "text": "A smaller selection for a more exact feeling.",
        "image": "main/img/hero-subcategory.webp",
    },
    "item": {
        "kicker": "zad Item",
        "title": "",
        "text": "",
        "image": "main/img/hero-gifts.webp",
    },
    "contact": {
        "kicker": "Contact zad",
        "title": "Let’s Arrange It",
        "text": "For availability, timing and order details.",
        "image": "main/img/hero-contact.webp",
    },
    "events": {
        "kicker": "zad Events",
        "title": "Gathered With Feeling",
        "text": "Workshops, gatherings and soft zad experiences.",
        "image": "main/img/hero-events.webp",
    },
    "blog": {
        "kicker": "ZAD JOURNAL",
        "title": "مجله زاد",
        "text": "راهنماها و یادداشت‌هایی برای انتخاب گل، هدیه و لحظه‌های خاص.",
        "image": "main/img/hero-contact.webp",
    },
    "faq": {
        "kicker": "zad Help",
        "title": "Little Answers",
        "text": "Simple answers before you call or order.",
        "image": "main/img/hero-faq.webp",
    },
    "mashhad": {
        "kicker": "ZAD MASHHAD",
        "title": "زاد در مشهد",
        "text": "هماهنگی سریع سفارش گل، هدیه و ارسال همان‌روز در مشهد.",
        "image": "main/img/hero-mashhad.webp",
    },
    "about": {
        "kicker": "zad Concept Store",
        "title": "The Story of zad",
        "text": "A closer look at the care behind the brand.",
        "image": "main/img/hero-about.webp",
    },
}


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
