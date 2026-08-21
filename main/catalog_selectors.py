from .models import Product


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
