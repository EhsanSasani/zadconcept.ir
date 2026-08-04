"""Products HTTP views.

Extracted from the historical view module; shared presentation policy remains in
``main.views.legacy`` until its dedicated lower layer is complete.
"""

from .support import (
    Category,
    Flower,
    Product,
    SECTION_CATEGORY_ROUTE_NAMES,
    SECTION_CONTENT,
    _default_context,
    _get_site_hero,
    _hero_from_key,
    _item_telegram_href,
    _published_products,
    _section_category_url,
    get_object_or_404,
    product_node,
    redirect,
    render,
    reverse,
)

def _item_detail_context(request, product):
    category = product.category
    category_name = category.name if category else "Product"
    section = category.section if category else ""
    active_nav = section if section in SECTION_CONTENT else ""

    subcategory_url = None
    subcategory_label = None

    if category and category.section in SECTION_CATEGORY_ROUTE_NAMES:
        subcategory_url = _section_category_url(category)
        subcategory_label = category.name

    breadcrumbs = [{"name": "Home", "url": reverse("index")}]

    if section and section in SECTION_CONTENT:
        breadcrumbs.append(
            {
                "name": SECTION_CONTENT[section]["title"],
                "url": reverse(section),
            }
        )

    if category and category.parent_id:
        breadcrumbs.append(
            {
                "name": category.parent.name,
                "url": _section_category_url(category.parent),
            }
        )

    if subcategory_url and subcategory_label:
        breadcrumbs.append(
            {
                "name": subcategory_label,
                "url": subcategory_url,
            }
        )

    breadcrumbs.append({"name": product.seo_name, "url": None})

    similar_items = list(
        _published_products()
        .filter(category=category)
        .exclude(pk=product.pk)
        .select_related("category")
        .prefetch_related("tags")
        .order_by("-featured", "sort_order", "-created_at")[:6]
    )

    if len(similar_items) < 3 and section:
        extra_items = list(
            _published_products()
            .filter(category__section=section)
            .exclude(pk=product.pk)
            .exclude(pk__in=[item.pk for item in similar_items])
            .select_related("category")
            .prefetch_related("tags")
            .order_by("-featured", "sort_order", "-created_at")[: 6 - len(similar_items)]
        )
        similar_items.extend(extra_items)

    description = product.seo_description

    context = _default_context(
        request,
        page_type="item",
        active_nav=active_nav,
        meta_title=f"{product.seo_name} | سفارش در مشهد",
        meta_description=product.seo_description,
        breadcrumbs=breadcrumbs,
        item_id=product.pk,
        enable_product_modal=True,
        content_page="product",
        schema_type="ItemPage",
        og_type="product",
        social_image=product.cover_image if product.cover_image else None,
    )

    hero_data = _hero_from_key(
        "item",
        title=product.seo_name,
        text=description,
        image=product.cover_image.url if getattr(product, "cover_image", None) else "main/img/hero-gifts.webp",
    )

    db_hero = _get_site_hero("item", product.slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "product": product,
            "category_name": category_name,
            "section_label": SECTION_CONTENT[section]["nav"].title() if section in SECTION_CONTENT else "Collection",
            "category_url": reverse(section) if section in SECTION_CONTENT else reverse("index"),
            "subcategory_url": subcategory_url,
            "subcategory_label": subcategory_label,
            "similar_items": similar_items,
            "item_telegram_href": _item_telegram_href(request, product),
            "item_call_text": "تماس",
            "item_telegram_text": "تلگرام",
            "mashhad_order_url": reverse("mashhad_flower_order"),
        }
    )

    context["structured_data_graph"].append(product_node(product))

    return context

def product_detail(request, pk: int, slug: str):
    product = get_object_or_404(
        _published_products()
        .select_related("category", "category__parent")
        .prefetch_related("tags", "gallery_images"),
        pk=pk,
    )

    return redirect(product.get_absolute_url(), permanent=True)

def _section_product_detail(request, section, category_slug, slug):
    product = get_object_or_404(
        _published_products()
        .filter(category__section=section)
        .select_related("category", "category__parent")
        .prefetch_related("tags", "gallery_images"),
        slug=slug,
    )

    if product.category.slug != category_slug:
        return redirect(product.get_absolute_url(), permanent=True)

    return render(request, "item_detail.html", _item_detail_context(request, product))

def flower_product_detail(request, category_slug, slug):
    return _section_product_detail(request, Category.Section.FLOWERS, category_slug, slug)

def bakery_product_detail(request, category_slug, slug):
    return _section_product_detail(request, Category.Section.BAKERY, category_slug, slug)

def gift_product_detail(request, category_slug, slug):
    return _section_product_detail(request, Category.Section.GIFTS, category_slug, slug)

def flower_detail(request, pk: int, slug: str):
    flower = get_object_or_404(
        Flower.objects.filter(
            is_active=True,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        .select_related("category")
        .prefetch_related("tags", "gallery_images"),
        pk=pk,
    )

    return redirect(flower.get_absolute_url(), permanent=True)

def flower_detail_redirect(request, pk: int):
    flower = get_object_or_404(
        Flower.objects.filter(
            is_active=True,
            publish_status=Product.PublishStatus.PUBLISHED,
        ),
        pk=pk,
    )

    return redirect(flower.get_absolute_url(), permanent=True)
