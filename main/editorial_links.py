"""Contextual links back to deliberately curated, public guides."""
from django.db.models import Q

from .editorial import public_posts


def guides_for_product(product):
    return public_posts().filter(
        Q(product_connections__product=product) | Q(primary_category_id=product.category_id)
    ).distinct()[:4]


def guides_for_category(category):
    return public_posts().filter(primary_category=category)[:4]
