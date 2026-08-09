"""Landing and collection views for the independent Wedding catalog."""

from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from ..content.weddings import (
    WEDDING_COLLECTIONS,
    WEDDING_META_DESCRIPTION,
    WEDDING_META_TITLE,
)
from ..models import WeddingPageContent
from ..selectors.weddings import (
    current_wedding_content,
    wedding_collection_content,
    wedding_products_by_type,
    wedding_products_for_type,
)
from .support import _default_context, _with_home


def _wedding_content_and_gallery():
    try:
        managed_content = current_wedding_content()
    except DatabaseError:
        managed_content = None

    content = managed_content or WeddingPageContent()
    try:
        gallery = list(content.gallery_images.all()) if content.pk else []
    except DatabaseError:
        gallery = []
    return content, gallery


def _landing_collections():
    try:
        products_by_type = wedding_products_by_type()
    except DatabaseError:
        products_by_type = {}

    collections = []
    for slug, config in WEDDING_COLLECTIONS.items():
        products = products_by_type.get(config["type"], [])
        collections.append(
            {
                **config,
                "slug": slug,
                "url": reverse("wedding_collection", args=[slug]),
                "preview_product": products[0] if products else None,
                "product_count": len(products),
            }
        )
    return collections


def weddings(request):
    wedding_content, wedding_gallery = _wedding_content_and_gallery()
    meta_title = (wedding_content.seo_title or "").strip() or WEDDING_META_TITLE
    meta_description = (
        (wedding_content.meta_description or "").strip()
        or WEDDING_META_DESCRIPTION
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
            "wedding_collections": _landing_collections(),
        }
    )
    return render(request, "weddings.html", context)


def wedding_collection(request, collection_slug):
    config = WEDDING_COLLECTIONS.get(collection_slug)
    if config is None:
        raise Http404("Wedding collection not found")

    try:
        managed_content = wedding_collection_content(collection_slug)
        products = list(wedding_products_for_type(config["type"]))
    except DatabaseError:
        managed_content = None
        products = []

    if managed_content:
        hero_kicker = managed_content.hero_kicker
        hero_title = managed_content.hero_title
        hero_text = managed_content.hero_text
        hero_alt_text = managed_content.hero_alt_text
        hero_image = managed_content.hero_image or None
        hero_mobile_image = managed_content.hero_mobile_image or None
        managed_seo_title = (managed_content.seo_title or "").strip()
        managed_meta_description = (
            managed_content.meta_description or ""
        ).strip()
    else:
        hero_kicker = config["kicker"]
        hero_title = config["title"]
        hero_text = config["description"]
        hero_alt_text = config["title"]
        hero_image = None
        hero_mobile_image = None
        managed_seo_title = ""
        managed_meta_description = ""

    collection = {
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
        value.strip()
        for value in (hero_kicker or "", hero_title or "", hero_text or "")
    )
    breadcrumbs = _with_home(
        [
            {"name": "عروسی", "url": reverse("weddings")},
            {"name": config["title"], "url": None},
        ]
    )
    social_image = hero_image or (
        products[0].cover_image
        if products and products[0].cover_image
        else None
    )

    context = _default_context(
        request,
        page_type="wedding_collection",
        active_nav="weddings",
        meta_title=managed_seo_title or f"{config['title']} در مشهد | زاد",
        meta_description=managed_meta_description or config["description"],
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        schema_type="CollectionPage",
        social_image=social_image,
        suppress_default_hero=True,
    )
    context.update(
        {
            "collection": collection,
            "collection_content": managed_content,
            "collection_has_copy": collection_has_copy,
            "products": products,
        }
    )
    return render(request, "wedding_collection.html", context)
