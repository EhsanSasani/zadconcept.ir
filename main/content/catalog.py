"""Catalog copy and stable presentation configuration."""

from ..models import Category

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

CATEGORY_SLUG_ALIASES = {
    "plant": "plants",
    "wreath": "stand",
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

CATALOG_PAGE_SIZE = 12

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
    "no-occasion": {
        "title": "بدون مناسبت",
        "hero_title": "گل بدون مناسبت",
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
    "no-occasion": "Just Because",
}

OCCASION_DETAIL_HERO_IMAGE = "main/img/occasion-detail-hero-v1.webp"

OCCASION_DETAIL_HERO_MOBILE_IMAGE = "main/img/occasion-detail-hero-mobile-v1.webp"

FLOWER_FILTER_ORDER = [
    "hand-bouquet",
    "box",
    "bouquet",
    "jarl",
    "stand",
    "plants",
]
