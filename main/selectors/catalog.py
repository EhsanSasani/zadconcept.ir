"""Read-only catalog policy for every public product discovery surface.

``published_products`` is the direct-access contract used by product detail
pages and the product sitemap. ``catalog_products`` is the generic discovery
contract used by home, catalog, occasion, local, blog, and related-product
lists. Keeping those contracts separate lets a dedicated campaign domain hide
products from generic discovery without breaking their canonical detail URLs.
"""

from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When

from ..content.catalog import FLOWER_FILTER_ORDER
from ..models import Category, Product, Tag


DEDICATED_OCCASION_SLUGS = frozenset({"wedding"})
DEFAULT_PRODUCT_ORDER = ("-featured", "sort_order", "-created_at", "id")


def published_products():
    """Return products whose canonical detail URLs may be served publicly."""

    return Product.objects.published()


def catalog_products():
    """Return products discoverable in generic lists, with card relations ready."""

    return published_products().with_card_relations()


def catalog_products_for_section(section):
    """Return discoverable products for one physical catalog section."""

    return catalog_products().for_section(section)


def catalog_products_for_occasion(occasion, *, section=None):
    """Return discoverable products assigned to one active occasion."""

    queryset = catalog_products().filter(tags=occasion)
    if section:
        queryset = queryset.filter(category__section=section)
    return queryset.distinct()


def product_detail_products():
    """Return direct-access products with every detail-page relation eager loaded."""

    return published_products().with_detail_relations()


def ordered_catalog_products(queryset):
    """Apply the default stable editorial ordering for product cards."""

    return queryset.order_by(*DEFAULT_PRODUCT_ORDER)


def ordered_section_catalog_products(queryset, section):
    """Apply the section landing order, including the curated flower taxonomy."""

    if section != Category.Section.FLOWERS:
        return ordered_catalog_products(queryset)

    category_order = {
        slug: index for index, slug in enumerate(FLOWER_FILTER_ORDER)
    }
    category_cases = [
        When(category__slug=slug, then=Value(index))
        for slug, index in category_order.items()
    ]
    return queryset.annotate(
        category_rank=Case(
            *category_cases,
            default=Value(len(category_order)),
            output_field=IntegerField(),
        )
    ).order_by(
        "category_rank",
        *DEFAULT_PRODUCT_ORDER,
    )


def catalog_categories(section=None):
    """Return categories discoverable in generic catalog navigation."""

    queryset = Category.objects.filter(
        Q(parent__isnull=True) | Q(parent__is_active=True),
        is_active=True,
    )
    if section:
        queryset = queryset.filter(section=section)
    return queryset.order_by("section", "sort_order", "name")


def catalog_categories_with_child_state(section=None):
    """Return discoverable categories with an N+1-safe child-card flag."""

    active_children = Category.objects.filter(
        parent_id=OuterRef("pk"),
        is_active=True,
    )
    return catalog_categories(section).annotate(
        has_active_children=Exists(active_children)
    )


def active_root_categories(section):
    """Return active top-level categories in their editorial order."""

    return catalog_categories_with_child_state(section).filter(parent__isnull=True)


def active_child_categories(category):
    """Return active direct children with the category-card query contract."""

    return catalog_categories_with_child_state(category.section).filter(
        parent=category
    )


def catalog_occasion_tags():
    """Return occasion tags discoverable outside dedicated campaign domains."""

    return (
        Tag.objects.filter(is_occasion=True, is_active=True)
        .exclude(Q(slug__in=DEDICATED_OCCASION_SLUGS) | Q(name="عروسی"))
        .order_by("sort_order", "name")
    )


def active_occasion_tags(limit=None):
    """Return public occasion tags as a template-ready list."""

    queryset = catalog_occasion_tags()
    return list(queryset[:limit] if limit else queryset)


def same_day_flower_products():
    """Return the admin-selected same-day flower collection."""

    return (
        catalog_products_for_section(Category.Section.FLOWERS)
        .same_day()
        .order_by("-featured", "sort_order", "-updated_at", "id")
    )


def products_for_category(category):
    """Return public products for a leaf or its two-level category tree."""

    queryset = catalog_products_for_section(category.section)
    if category.parent_id:
        return queryset.filter(category=category)
    return queryset.filter(Q(category=category) | Q(category__parent=category))


def related_catalog_products(product, *, limit=6):
    """Return a stable related rail from the product's discovery cohort."""

    return list(
        catalog_products()
        .filter(category__section=product.category.section)
        .exclude(pk=product.pk)
        .annotate(
            relation_rank=Case(
                When(category_id=product.category_id, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("relation_rank", *DEFAULT_PRODUCT_ORDER)[:limit]
    )
