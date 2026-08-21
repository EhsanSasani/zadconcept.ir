from django.urls import reverse

from .page_presentation import OCCASION_CARD_CONTENT, OCCASION_EN_LABELS


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
