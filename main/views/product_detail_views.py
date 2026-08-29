from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..category_presentation import SECTION_CATEGORY_ROUTE_NAMES, _section_category_url
from ..catalog_selectors import _published_products, _published_same_day_products
from ..managed_heroes import _get_site_hero
from ..models import Category, Product
from ..page_context import _default_context
from ..page_presentation import SECTION_CONTENT, _hero_from_key
from ..seo import product_node


def _telegram_href():
    return getattr(settings, "zad_TELEGRAM_URL", "https://t.me/Flowerhouse_pv")

def _item_telegram_href(request, product):
    return _telegram_href()

def _item_detail_context(request, product):
    category = product.category
    category_name = category.name if category else "Product"
    section = category.section if category else ""
    subcategory_url = None
    subcategory_label = None
    breadcrumbs = [{"name": "Home", "url": reverse("index")}]

    if product.is_wedding:
        active_nav = "weddings"
        section_label = "Weddings"
        category_url = reverse("weddings")
        breadcrumbs.append({"name": "عروسی", "url": category_url})

        wedding_related = (
            Product.objects.valid_weddings()
            .published()
            .exclude(pk=product.pk)
            .select_related("category")
            .prefetch_related("tags")
        )
        similar_items = list(
            wedding_related.filter(wedding_type=product.wedding_type).order_by(
                "wedding_sort_order",
                "sort_order",
                "-created_at",
                "id",
            )[:6]
        )
        if len(similar_items) < 6:
            extra_items = list(
                wedding_related.exclude(
                    pk__in=[item.pk for item in similar_items]
                ).order_by(
                    "wedding_sort_order",
                    "sort_order",
                    "-created_at",
                    "id",
                )[: 6 - len(similar_items)]
            )
            similar_items.extend(extra_items)
    elif product.is_same_day:
        active_nav = Category.Section.FLOWERS
        section_label = "ارسال روز"
        category_url = reverse("flowers_same_day")
        breadcrumbs.extend(
            [
                {"name": "گل‌ها", "url": reverse("flowers")},
                {"name": "ارسال امروز", "url": category_url},
            ]
        )
        similar_items = list(
            _published_same_day_products()
            .exclude(pk=product.pk)
            .select_related("category")
            .prefetch_related("tags")
            .order_by("-featured", "sort_order", "-created_at")[:6]
        )
    else:
        active_nav = section if section in SECTION_CONTENT else ""
        section_label = (
            SECTION_CONTENT[section]["nav"].title()
            if section in SECTION_CONTENT
            else "Collection"
        )
        category_url = (
            reverse(section) if section in SECTION_CONTENT else reverse("index")
        )

        if category and category.section in SECTION_CATEGORY_ROUTE_NAMES:
            subcategory_url = _section_category_url(category)
            subcategory_label = category.name

        if section and section in SECTION_CONTENT:
            breadcrumbs.append(
                {
                    "name": SECTION_CONTENT[section]["title"],
                    "url": category_url,
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
                .order_by("-featured", "sort_order", "-created_at")[
                    : 6 - len(similar_items)
                ]
            )
            similar_items.extend(extra_items)

    breadcrumbs.append({"name": product.seo_name, "url": None})

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
            "product_tags": product.tags.filter(is_active=True).order_by(
                "sort_order",
                "name",
            ),
            "category_name": category_name,
            "section_label": section_label,
            "category_url": category_url,
            "subcategory_url": subcategory_url,
            "subcategory_label": subcategory_label,
            "similar_items": similar_items,
            "item_telegram_href": _item_telegram_href(request, product),
            "item_call_text": "تماس",
            "item_telegram_text": "تلگرام",
            "mashhad_order_url": reverse("mashhad_flower_order"),
        }
    )

    if product.has_price:
        context["structured_data_graph"].append(product_node(product))

    return context

def _section_product_detail(request, section, category_slug, slug):
    products = (
        Product.objects.published()
        .select_related("category", "category__parent")
        .prefetch_related("tags", "gallery_images")
    )

    # Preserve the existing SEO/canonical contract: the current product slug
    # remains the primary public identifier. product_code is accepted only as
    # a stable, human-facing alias and is permanently redirected to canonical.
    try:
        product = products.get(slug=slug)
    except Product.DoesNotExist:
        product = get_object_or_404(products, product_code=slug)

    canonical_section = product.canonical_section or product.category.section
    canonical_category_slug = (
        product.canonical_category_slug or product.category.slug
    )
    if (
        slug != product.slug
        or canonical_section != section
        or canonical_category_slug != category_slug
    ):
        return redirect(product.get_absolute_url(), permanent=True)

    return render(request, "main/pages/products/detail.html", _item_detail_context(request, product))

def flower_product_detail(request, category_slug, slug):
    return _section_product_detail(request, Category.Section.FLOWERS, category_slug, slug)

def bakery_product_detail(request, category_slug, slug):
    return _section_product_detail(request, Category.Section.BAKERY, category_slug, slug)

def gift_product_detail(request, category_slug, slug):
    return _section_product_detail(request, Category.Section.GIFTS, category_slug, slug)
