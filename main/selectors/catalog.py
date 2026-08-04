"""Catalog query policy.

Every public product list must start from these selectors so publication,
category activity, eager-loading, and campaign visibility cannot drift between
pages.
"""

from django.db.models import Q

from ..models import Category, Product, SAME_DAY_TAG_SLUG, Tag


def published_products():
    """Return the global public product contract without page ordering."""

    return Product.objects.filter(
        is_active=True,
        publish_status=Product.PublishStatus.PUBLISHED,
        category__is_active=True,
    )


def published_products_for_section(section):
    """Return public products for one physical catalog section."""

    return (
        published_products()
        .filter(category__section=section)
        .select_related("category")
        .prefetch_related("tags")
    )


def active_root_categories(section):
    """Return active top-level categories in their editorial order."""

    return Category.objects.filter(
        section=section,
        is_active=True,
        parent__isnull=True,
    ).order_by("sort_order", "name")


def active_occasion_tags(limit=None):
    """Return public occasion tags; wedding is a dedicated domain."""

    queryset = (
        Tag.objects.filter(is_occasion=True, is_active=True)
        .exclude(Q(slug="wedding") | Q(name="عروسی"))
        .order_by("sort_order", "name")
    )
    return list(queryset[:limit] if limit else queryset)


def same_day_flower_products():
    """Return the admin-selected same-day flower collection."""

    return (
        published_products_for_section(Category.Section.FLOWERS)
        .filter(tags__slug=SAME_DAY_TAG_SLUG)
        .distinct()
        .order_by("-featured", "sort_order", "-created_at")
    )


def products_for_category(category):
    """Return public products for a leaf or its two-level category tree."""

    queryset = published_products_for_section(category.section)
    if category.parent_id:
        return queryset.filter(category=category)
    return queryset.filter(Q(category=category) | Q(category__parent=category)).distinct()
