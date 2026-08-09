"""Read-only policy for the independent Wedding catalog."""

from collections import defaultdict

from django.db.models import Case, IntegerField, Value, When

from ..models import Product, WeddingCollectionContent, WeddingPageContent


WEDDING_PRODUCT_ORDER = (
    "wedding_sort_order",
    "sort_order",
    "-created_at",
    "id",
)


def wedding_products():
    """Return public, fully typed Wedding products with card relations loaded."""

    return (
        Product.objects.valid_weddings()
        .published()
        .with_card_relations()
        .order_by(*WEDDING_PRODUCT_ORDER)
    )


def wedding_products_for_type(wedding_type):
    return wedding_products().filter(wedding_type=wedding_type)


def related_wedding_products(product, *, limit=6):
    """Prioritize the same Wedding collection without crossing catalog scope."""

    return list(
        wedding_products()
        .exclude(pk=product.pk)
        .annotate(
            collection_rank=Case(
                When(wedding_type=product.wedding_type, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("collection_rank", *WEDDING_PRODUCT_ORDER)[:limit]
    )


def wedding_products_by_type():
    """Group the landing catalog in one database query."""

    grouped = defaultdict(list)
    for product in wedding_products():
        grouped[product.wedding_type].append(product)
    return grouped


def current_wedding_content():
    return WeddingPageContent.current()


def wedding_collection_content(collection_slug):
    return WeddingCollectionContent.objects.filter(
        collection_key=collection_slug
    ).first()
