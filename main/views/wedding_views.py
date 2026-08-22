from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from ..catalog_selectors import _published_products_for_section
from ..models import Category, Product, PROPOSAL_COLLECTION_TAG_SLUG, WeddingCollectionContent, WeddingPageContent
from ..page_context import _default_context, _with_home
from .catalog_views import FLOWER_FILTER_ORDER, _catalog_ordered_products, _filter_links_for_categories


WEDDING_COLLECTIONS = {
    "proposal-bouquets": {
        "type": Product.WeddingType.PROPOSAL_BOUQUET,
        "title": "دسته‌گل خواستگاری و بله‌برون",
        "short_title": "گل خواستگاری و بله‌برون",
        "kicker": "PROPOSAL BOUQUETS",
        "description": "دسته‌گل‌هایی هماهنگ با فضای خواستگاری و بله‌برون؛ با امکان هماهنگی رنگ، فرم و بودجه.",
        "fallback_image": "main/img/sub-bridal-bouquet.webp",
        "number": "01",
    },
    "proposal-sweets": {
        "type": Product.WeddingType.PROPOSAL_SWEETS,
        "title": "شیرینی خواستگاری و بله‌برون",
        "short_title": "شیرینی خواستگاری",
        "kicker": "PROPOSAL SWEETS",
        "description": "شیرینی‌های منتخب برای پذیرایی و هدیه، با امکان هماهنگی تعداد و چیدمان.",
        "fallback_image": "main/img/cat-bakery.webp",
        "number": "02",
    },
    "bridal-bouquets": {
        "type": Product.WeddingType.BRIDAL_BOUQUET,
        "title": "دسته‌گل عروس",
        "short_title": "دسته‌گل عروس",
        "kicker": "BRIDAL BOUQUETS",
        "description": "طراحی دسته‌گل عروس متناسب با استایل، فصل و پالت رنگ روز عروسی.",
        "fallback_image": "main/img/sub-bridal-bouquet.webp",
        "number": "03",
    },
    "wedding-cars": {
        "type": Product.WeddingType.WEDDING_CAR,
        "title": "ماشین عروس",
        "short_title": "ماشین عروس",
        "kicker": "WEDDING CARS",
        "description": "گل‌آرایی اختصاصی خودرو با توجه به مدل ماشین، فصل و سبک مراسم.",
        "fallback_image": "main/img/sub-stand.webp",
        "number": "04",
    },
}

def _published_wedding_products(wedding_type):
    wedding_products = list(
        Product.objects.valid_weddings()
        .published()
        .filter(wedding_type=wedding_type)
        .select_related("category")
        .prefetch_related("tags")
        .order_by(
            "wedding_sort_order",
            "sort_order",
            "-created_at",
            "id",
        )
    )

    if wedding_type != Product.WeddingType.PROPOSAL_BOUQUET:
        return wedding_products

    selected_general_products = _catalog_ordered_products(
        _published_products_for_section(Category.Section.FLOWERS)
        .filter(tags__slug=PROPOSAL_COLLECTION_TAG_SLUG)
        .distinct(),
        Category.Section.FLOWERS,
    )
    return wedding_products + list(selected_general_products)

def _proposal_collection_filter_data(request, products, collection_slug):
    general_products = [
        product
        for product in products
        if product.catalog_scope == Product.CatalogScope.GENERAL
    ]
    available_category_ids = {
        product.category_id for product in general_products if product.category_id
    }
    categories = list(
        Category.objects.for_general_catalog()
        .filter(
            pk__in=available_category_ids,
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        .order_by("sort_order", "name")
    )
    category_order = {
        slug: index for index, slug in enumerate(FLOWER_FILTER_ORDER)
    }
    categories.sort(
        key=lambda category: category_order.get(
            category.slug,
            len(category_order),
        )
    )

    selected_slug = request.GET.get("category") or ""
    selected_category = None
    filtered_products = products

    if selected_slug:
        selected_category = get_object_or_404(
            Category.objects.for_general_catalog(),
            section=Category.Section.FLOWERS,
            slug=selected_slug,
            is_active=True,
            pk__in=available_category_ids,
        )
        filtered_products = [
            product
            for product in general_products
            if product.category_id == selected_category.pk
        ]

    base_url = reverse("wedding_collection", args=[collection_slug])
    filter_links = (
        _filter_links_for_categories(
            base_url,
            categories,
            selected_slug=selected_slug,
        )
        if categories
        else []
    )
    return filtered_products, filter_links, selected_category

def _wedding_content_and_gallery():
    try:
        managed_content = WeddingPageContent.current()
    except DatabaseError:
        managed_content = None

    wedding_content = managed_content or WeddingPageContent()
    try:
        wedding_gallery = (
            list(wedding_content.gallery_images.all())
            if wedding_content.pk
            else []
        )
    except DatabaseError:
        wedding_gallery = []
    return wedding_content, wedding_gallery

def _managed_wedding_collection_content(collection_slug):
    try:
        return WeddingCollectionContent.objects.filter(
            collection_key=collection_slug
        ).first()
    except DatabaseError:
        return None

def weddings(request):
    wedding_content, wedding_gallery = _wedding_content_and_gallery()

    collections = []
    collection_products = []
    try:
        for slug, config in WEDDING_COLLECTIONS.items():
            products = _published_wedding_products(config["type"])
            collection_products.append(products)
            collections.append(
                {
                    **config,
                    "slug": slug,
                    "url": reverse("wedding_collection", args=[slug]),
                    "preview_product": products[0] if products else None,
                    "product_count": len(products),
                }
            )
    except DatabaseError:
        collections = [
            {
                **config,
                "slug": slug,
                "url": reverse("wedding_collection", args=[slug]),
                "preview_product": None,
                "product_count": 0,
            }
            for slug, config in WEDDING_COLLECTIONS.items()
        ]
        collection_products = []


    meta_title = (
        wedding_content.seo_title.strip()
        if wedding_content.seo_title
        else "محصولات عروسی، خواستگاری و بله‌برون در مشهد | زاد"
    )
    meta_description = (
        wedding_content.meta_description.strip()
        if wedding_content.meta_description
        else (
            "مجموعه اختصاصی زاد برای دسته‌گل عروس، گل‌آرایی ماشین عروس، "
            "دسته‌گل و شیرینی خواستگاری و بله‌برون در مشهد."
        )
    )
    social_image = wedding_content.open_graph_image or wedding_content.hero_image

    context = _default_context(
        request,
        page_type="weddings",
        active_nav="weddings",
        meta_title=meta_title,
        meta_description=meta_description,
        schema_type="CollectionPage",
        social_image=social_image or None,
        suppress_default_hero=True,
    )
    context.update(
        {
            "wedding_content": wedding_content,
            "wedding_gallery": wedding_gallery,
            "wedding_steps": wedding_content.steps,
            "wedding_collections": collections,
        }
    )
    return render(request, "main/pages/weddings/index.html", context)

def wedding_collection(request, collection_slug):
    config = WEDDING_COLLECTIONS.get(collection_slug)
    if config is None:
        raise Http404("Wedding collection not found")

    managed_content = _managed_wedding_collection_content(collection_slug)
    try:
        products = _published_wedding_products(config["type"])
    except DatabaseError:
        products = []

    filter_links = []
    selected_category = None
    if config["type"] == Product.WeddingType.PROPOSAL_BOUQUET:
        products, filter_links, selected_category = _proposal_collection_filter_data(
            request,
            products,
            collection_slug,
        )

    if managed_content:
        hero_kicker = managed_content.hero_kicker
        hero_title = managed_content.hero_title
        hero_text = managed_content.hero_text
        hero_alt_text = managed_content.hero_alt_text
        hero_image = managed_content.hero_image or None
        hero_mobile_image = managed_content.hero_mobile_image or None
        managed_seo_title = (managed_content.seo_title or "").strip()
        managed_meta_description = (managed_content.meta_description or "").strip()
    else:
        hero_kicker = config["kicker"]
        hero_title = config["title"]
        hero_text = config["description"]
        hero_alt_text = config["title"]
        hero_image = None
        hero_mobile_image = None
        managed_seo_title = ""
        managed_meta_description = ""

    collection_data = {
        **config,
        "slug": collection_slug,
        "hero_kicker": hero_kicker,
        "hero_title": hero_title,
        "hero_text": hero_text,
        "hero_alt_text": hero_alt_text or config["title"],
        "hero_image": hero_image,
        "hero_mobile_image": hero_mobile_image,
    }
    collection_has_copy = any(
        value.strip() for value in (hero_kicker or "", hero_title or "", hero_text or "")
    )

    breadcrumbs = _with_home(
        [
            {"name": "عروسی", "url": reverse("weddings")},
            {"name": config["title"], "url": None},
        ]
    )
    meta_title = managed_seo_title or f"{config['title']} در مشهد | زاد"
    meta_description = managed_meta_description or config["description"]
    social_image = hero_image or (products[0].cover_image if products and products[0].cover_image else None)

    context = _default_context(
        request,
        page_type="wedding_collection",
        active_nav="weddings",
        meta_title=meta_title,
        meta_description=meta_description,
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        schema_type="CollectionPage",
        social_image=social_image,
        suppress_default_hero=True,
    )
    context.update(
        {
            "collection": collection_data,
            "collection_content": managed_content,
            "collection_has_copy": collection_has_copy,
            "products": products,
            "filter_links": filter_links,
            "selected_category": selected_category,
        }
    )
    return render(request, "main/pages/weddings/collection.html", context)
