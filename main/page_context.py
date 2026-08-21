from django.urls import reverse

from .models import PageContentBlock
from .page_presentation import (
    _hero_defaults,
    _public_brand_copy,
)
from .seo import (
    base_graph,
    canonical_url,
    faq_node,
    robots_content,
    social_image_dimensions,
    social_image_url,
)


def _with_home(items):
    return [{"name": "Home", "url": reverse("index")}, *items]


def _default_context(
    request,
    *,
    page_type,
    active_nav,
    meta_title,
    meta_description,
    breadcrumbs=None,
    faq_items=None,
    include_faq_schema=False,
    item_id=None,
    enable_product_modal=False,
    content_page=None,
    schema_type="WebPage",
    og_type="website",
    social_image=None,
    language="fa-IR",
    html_lang="fa",
    html_dir="rtl",
    og_locale="fa_IR",
    alternate_links=None,
    hide_global_chrome=False,
    suppress_default_hero=False,
    is_indexable=True,
):
    page_canonical = canonical_url(request)
    structured_data_graph = base_graph(
        page_canonical,
        meta_title,
        meta_description,
        schema_type=schema_type,
        language=language,
    )
    social_width, social_height = social_image_dimensions(social_image)
    page_robots = robots_content(request) if is_indexable else "noindex,follow"
    context = {
        "page_type": page_type,
        "active_nav": active_nav,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "canonical_url": page_canonical,
        "robots_content": page_robots,
        "og_type": og_type,
        "og_locale": og_locale,
        "social_image_url": social_image_url(social_image),
        "social_image_width": social_width,
        "social_image_height": social_height,
        "item_id": item_id,
        "structured_data_graph": structured_data_graph,
        "is_homepage": False,
        "enable_product_modal": enable_product_modal,
        "flowers_url": reverse("flowers"),
        "html_lang": html_lang,
        "html_dir": html_dir,
        "alternate_links": alternate_links or [],
        "hide_global_chrome": hide_global_chrome,
        "suppress_default_hero": suppress_default_hero,
        "has_managed_site_hero": False,
        "page_content": {
            block.section_key: {
                "kicker": _public_brand_copy(block.kicker),
                "title": _public_brand_copy(block.title),
                "body": _public_brand_copy(block.body),
                "cta_text": _public_brand_copy(block.cta_text),
                "cta_url": block.cta_url,
            }
            for block in PageContentBlock.objects.filter(
                page=content_page or page_type,
                is_active=True,
            ).order_by("sort_order", "section_key")
        },
        **_hero_defaults(meta_title, meta_description),
    }

    if breadcrumbs:
        # Breadcrumb context is retained for a future visible UI component.
        # No BreadcrumbList JSON-LD is emitted while the visual breadcrumb is disabled.
        context["breadcrumbs"] = breadcrumbs

    if faq_items:
        context["faq_items"] = faq_items
        if include_faq_schema:
            structured_data_graph.append(
                faq_node(faq_items, page_canonical, language=language)
            )

    return context
