from .models import Category, Product, Tag


def _published_products():
    """Return only products that belong to the public general catalog."""

    return Product.objects.for_general_catalog().published()


def _published_products_for_section(section):
    return (
        _published_products()
        .filter(category__section=section)
        .select_related("category")
        .prefetch_related("tags")
    )


def _active_occasion_tags(limit=None):
    queryset = Tag.objects.for_general_catalog().filter(
        is_occasion=True,
        is_active=True,
    ).order_by("sort_order", "name")

    if limit:
        queryset = queryset[:limit]

    return list(queryset)


def _active_categories_for_section(section):
    queryset = Category.objects.for_general_catalog().filter(
        section=section,
        is_active=True,
        parent__isnull=True,
    )

    return queryset.order_by("sort_order", "name")
