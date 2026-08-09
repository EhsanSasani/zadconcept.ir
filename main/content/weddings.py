"""Stable copy and routing metadata for the Wedding catalog."""

from ..models import (
    BAKERY_WEDDING_CATEGORY_SLUGS,
    FLOWER_PROTECTED_WEDDING_CATEGORY_SLUGS,
    Product,
    WEDDING_LEGACY_TAG_SLUGS,
)


WEDDING_FLOWER_LEGACY_SLUGS = frozenset(
    (*FLOWER_PROTECTED_WEDDING_CATEGORY_SLUGS, *WEDDING_LEGACY_TAG_SLUGS)
)
WEDDING_BAKERY_LEGACY_SLUGS = frozenset(
    (*BAKERY_WEDDING_CATEGORY_SLUGS, *WEDDING_LEGACY_TAG_SLUGS)
)


WEDDING_COLLECTIONS = {
    "proposal-bouquets": {
        "type": Product.WeddingType.PROPOSAL_BOUQUET,
        "title": "گل‌های خواستگاری و بله‌برون",
        "short_title": "گل‌های خواستگاری و بله‌برون",
        "kicker": "PROPOSAL BOUQUETS",
        "description": (
            "دسته‌گل‌هایی هماهنگ با فضای خواستگاری و بله‌برون؛ "
            "با امکان هماهنگی رنگ، فرم و بودجه."
        ),
        "fallback_image": "main/img/sub-bridal-bouquet.webp",
        "number": "01",
    },
    "proposal-sweets": {
        "type": Product.WeddingType.PROPOSAL_SWEETS,
        "title": "شیرینی خواستگاری و بله‌برون",
        "short_title": "شیرینی خواستگاری",
        "kicker": "PROPOSAL SWEETS",
        "description": (
            "شیرینی‌های منتخب برای پذیرایی و هدیه، "
            "با امکان هماهنگی تعداد و چیدمان."
        ),
        "fallback_image": "main/img/cat-bakery.webp",
        "number": "02",
    },
    "bridal-bouquets": {
        "type": Product.WeddingType.BRIDAL_BOUQUET,
        "title": "دسته‌گل عروس",
        "short_title": "دسته‌گل عروس",
        "kicker": "BRIDAL BOUQUETS",
        "description": (
            "طراحی دسته‌گل عروس متناسب با استایل، فصل و پالت رنگ روز عروسی."
        ),
        "fallback_image": "main/img/sub-bridal-bouquet.webp",
        "number": "03",
    },
    "wedding-cars": {
        "type": Product.WeddingType.WEDDING_CAR,
        "title": "ماشین عروس",
        "short_title": "ماشین عروس",
        "kicker": "WEDDING CARS",
        "description": (
            "گل‌آرایی اختصاصی خودرو با توجه به مدل ماشین، فصل و سبک مراسم."
        ),
        "fallback_image": "main/img/sub-stand.webp",
        "number": "04",
    },
}

WEDDING_COLLECTION_SLUG_BY_TYPE = {
    config["type"]: slug for slug, config in WEDDING_COLLECTIONS.items()
}


WEDDING_META_TITLE = "محصولات عروسی، خواستگاری و بله‌برون در مشهد | زاد"
WEDDING_META_DESCRIPTION = (
    "مجموعه اختصاصی زاد برای دسته‌گل عروس، گل‌آرایی ماشین عروس، "
    "دسته‌گل و شیرینی خواستگاری و بله‌برون در مشهد."
)
