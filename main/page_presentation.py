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


OCCASION_CARD_CONTENT = {
    "birthday": {
        "title": "تولد",
        "hero_title": "گل تولد",
        "intro": "برای شادی‌های روشن.",
        "hero_text": "برای لحظه‌ای که باید با گل، رنگ و یک یاد شیرین ماندگار شود.",
        "image": "main/img/occasions/birthday.webp",
    },
    "romantic": {
        "title": "عاشقانه",
        "hero_title": "گل عاشقانه",
        "intro": "برای لحظه‌های نزدیک.",
        "hero_text": "برای گفتن دوستت دارم؛ آرام‌تر و زیباتر از هر کلمه.",
        "image": "main/img/occasions/romantic.webp",
    },
    "congratulation": {
        "title": "تبریک",
        "hero_title": "گل تبریک",
        "intro": "برای خبرهای خوب.",
        "hero_text": "برای جشن گرفتن خبرهای خوب و شروع‌های روشن.",
        "image": "main/img/occasions/special.webp",
    },
    "apology": {
        "title": "معذرت‌خواهی",
        "hero_title": "گل معذرت‌خواهی",
        "intro": "برای دلجویی آرام.",
        "hero_text": "برای وقتی که یک انتخاب صمیمی، آغاز دوباره‌ی گفت‌وگوست.",
        "image": "main/img/occasions/special.webp",
    },
    "condolence": {
        "title": "ترحیم",
        "hero_title": "گل ترحیم",
        "intro": "برای همراهی محترمانه.",
        "hero_text": "برای ابراز همدلی؛ باوقار، آرام و محترمانه.",
        "image": "main/img/occasions/condolence.webp",
    },
    "proposal": {
        "title": "خواستگاری",
        "hero_title": "گل خواستگاری",
        "intro": "برای شروعی رسمی.",
        "hero_text": "برای شروعی به‌یادماندنی، با جزئیاتی ظریف و باشکوه.",
        "image": "main/img/occasions/special.webp",
    },
    "engagement": {
        "title": "بله‌برون",
        "hero_title": "گل بله‌برون",
        "intro": "برای پیمان‌های شیرین.",
        "hero_text": "برای جشنی صمیمی و شیرین در آغاز یک همراهی.",
        "image": "main/img/occasions/special.webp",
    },
    "formal-visit": {
        "title": "دیدار رسمی",
        "hero_title": "گل برای دیدار رسمی",
        "intro": "برای دیدارهایی محترمانه و سنجیده.",
        "hero_text": "انتخاب‌هایی آراسته و متعادل برای دیدارهای رسمی و حرفه‌ای.",
        "image": "main/img/occasions/special.webp",
    },
    "no-occasion": {
        "title": "بی‌بهانه",
        "hero_title": "گل بی‌بهانه",
        "intro": "برای بی‌دلیل دوست داشتن.",
        "hero_text": "برای همان روزهای معمولی که با یک یاد کوچک، خاص می‌شوند.",
        "image": "main/img/occasions/special.webp",
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
    "formal-visit": "Formal Visit",
    "no-occasion": "Just Because",
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
        "page_hero_style_class": "hero-style--occasion-detail",
        "page_hero_content_position": "center-right",
        "page_hero_mobile_content_position": "bottom-right",
    }


CATEGORY_CONTENT_OVERRIDES = {
    "hand-bouquet": {
        "label": "دسته گل",
        "meta_title": "دسته گل لوکس در مشهد | ZAD",
        "meta_description": "دسته‌گل‌های منتخب استودیو گل زاد برای هدیه، تولد، عاشقانه و لحظه‌های روزمره در مشهد.",
        "intro": "انتخابی نرم و روشن برای هدیه‌های روزمره و لحظه‌های خاص.",
        "image": "main/img/sub-bouquet.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
    "box": {
        "label": "باکس گل",
        "meta_title": "باکس گل لوکس در مشهد | ZAD",
        "meta_description": "باکس‌های گل استودیو گل زاد با چیدمان مینیمال، مناسب هدیه و سفارش سریع در مشهد.",
        "intro": "هدیه‌ای مرتب، شیک و آماده برای ارسال.",
        "image": "main/img/sub-box.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
    "bouquet": {
        "label": "بوکت",
        "meta_title": "بوکت گل خاص در مشهد | ZAD",
        "meta_description": "بوکت‌های طراحی‌شده زاد برای انتخاب‌های خاص‌تر و لوکس‌تر.",
        "intro": "چیدمانی طراحی‌شده‌تر برای وقتی که انتخاب باید خاص‌تر باشد.",
        "image": "main/img/sub-bouquet.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
    "stand": {
        "label": "استند گل",
        "meta_title": "استند گل در مشهد | ZAD",
        "meta_description": "استندهای گل رسمی زاد برای مراسم، ترحیم، افتتاحیه و لحظه‌های تشریفاتی.",
        "intro": "برای موقعیت‌های رسمی، محترمانه و پررنگ‌تر.",
        "image": "main/img/sub-stand.webp",
        "hero_image": "main/img/hero-subcategory.webp",
        },

    "wedding": {
        "label": "عروسی",
        "meta_title": "گل‌آرایی عروسی در مشهد | ZAD",
        "meta_description": "مجموعه عروسی زاد شامل دسته‌گل عروس و گل‌آرایی ماشین عروس در مشهد.",
        "intro": "انتخاب دسته‌گل عروس یا گل‌آرایی ماشین عروس برای روزی به‌یادماندنی.",
        "image": "main/img/sub-bridal-bouquet.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
    "wedding-car": {
        "label": "ماشین عروس",
        "meta_title": "گل‌آرایی ماشین عروس در مشهد | ZAD",
        "meta_description": "مدل‌های گل‌آرایی ماشین عروس زاد با طراحی هماهنگ و اجرای اختصاصی در مشهد.",
        "intro": "گل‌آرایی هماهنگ و اختصاصی برای ماشین عروس.",
        "image": "main/img/sub-stand.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
    "bridal-bouquet": {
        "label": "دسته‌گل عروس",
        "meta_title": "دسته‌گل عروس در مشهد | ZAD",
        "meta_description": "دسته‌گل عروس زاد با چیدمان لطیف، مینیمال و هماهنگ با مراسم.",
        "intro": "دسته‌گلی لطیف و هماهنگ برای یکی از مهم‌ترین لحظه‌ها.",
        "image": "main/img/sub-bridal-bouquet.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
    "jarl": {
        "label": "جار گل",
        "meta_title": "جار گل در مشهد | ZAD",
        "meta_description": "جارهای گل استودیو گل زاد برای دکور، هدیه‌های خاص و انتخاب‌های متفاوت.",
        "intro": "فرمی متفاوت و دکوراتیو برای انتخاب‌های خاص‌تر.",
        "image": "main/img/sub-box.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
    "plants": {
        "label": "گیاه",
        "meta_title": "گیاه هدیه‌ای در مشهد | ZAD",
        "meta_description": "گیاه‌های انتخاب‌شده زاد برای هدیه، خانه و لحظه‌های آرام‌تر.",
        "intro": "انتخابی ماندگارتر برای خانه، میز کار و هدیه‌های آرام‌تر.",
        "image": "main/img/sub-plant.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
    "basket": {
        "label": "سبد گل",
        "meta_title": "سبد گل در مشهد | ZAD",
        "meta_description": "سبدهای گل استودیو گل زاد برای هدیه و مراسم.",
        "intro": "یک دسته‌بندی قدیمی که فعلاً فقط برای سازگاری نگه داشته شده است.",
        "image": "main/img/sub-plant.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
    "birthday-cakes": {
        "label": "Birthday Cakes",
        "meta_title": "Birthday Cakes | ZAD",
        "meta_description": "ZAD birthday cakes for warm celebrations and soft moments.",
        "intro": "Soft cakes for warm birthday moments.",
        "image": "main/img/cat-bakery.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
    "cookies": {
        "label": "Cookies",
        "meta_title": "Cookies | ZAD",
        "meta_description": "ZAD cookies for gifting, gatherings and sweet little details.",
        "intro": "Small sweet bites for gentle celebrations.",
        "image": "main/img/cat-bakery.webp",
        "hero_image": "main/img/hero-subcategory.webp",
    },
}


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
