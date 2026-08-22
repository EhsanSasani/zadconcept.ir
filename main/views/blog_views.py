from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from ..catalog_selectors import (
    _active_categories_for_section,
    _published_products,
)
from ..managed_heroes import _get_site_hero
from ..models import Category, NewsPost, PublishStatus
from ..page_context import _default_context, _with_home
from ..page_presentation import _hero_from_key
from ..seo import article_node


def blog(request):
    posts = list(
        NewsPost.objects.filter(
            status=PublishStatus.PUBLISHED,
        ).order_by("-published_at", "-created_at")
    )

    breadcrumbs = _with_home([{"name": "Journal", "url": None}])
    db_hero = _get_site_hero("blog")

    context = _default_context(
        request,
        page_type="category",
        active_nav="",
        meta_title="مجله زاد | راهنمای گل، هدیه و مناسبت‌ها",
        meta_description="مطالب و راهنماهای زاد درباره گل، هدیه، نگهداری محصولات و برنامه‌ریزی مناسبت‌ها.",
        breadcrumbs=breadcrumbs,
        content_page="blog",
        suppress_default_hero=not db_hero,
    )

    if db_hero:
        context.update(db_hero)

    context["posts"] = posts

    return render(request, "main/pages/blog/index.html", context)


def blog_detail(request, slug):
    post = get_object_or_404(
        NewsPost,
        slug=slug,
        status=PublishStatus.PUBLISHED,
    )

    recommended_items = list(
        _published_products()
        .select_related("category")
        .prefetch_related("tags")
        .order_by("-featured", "sort_order", "-created_at")[:3]
    )

    flower_category = _active_categories_for_section(Category.Section.FLOWERS).first()

    recommended_subcategory = None

    if flower_category:
        recommended_subcategory = {
            "label": flower_category.name,
            "url": reverse("flower_subcategory", args=[flower_category.slug]),
        }

    breadcrumbs = _with_home(
        [
            {"name": "Journal", "url": reverse("blog")},
            {"name": post.title, "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="category",
        active_nav="",
        meta_title=f"{post.title} | مجله زاد",
        meta_description=post.excerpt or "مطالعه این مطلب از مجله زاد درباره گل، هدیه و مناسبت‌ها.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="blog-detail",
        og_type="article",
        social_image=post.cover_image if post.cover_image else None,
    )

    hero_data = _hero_from_key(
        "blog",
        title=post.title,
        text=post.excerpt or "Read a note from the zad Journal.",
        image=post.cover_image.url if post.cover_image else "main/img/hero-contact.webp",
    )

    db_hero = _get_site_hero("blog", post.slug)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)

    recommended_category = {"label": "Flowers", "url": reverse("flowers")}
    related_links = [recommended_category]

    if recommended_subcategory:
        related_links.append(recommended_subcategory)

    context.update(
        {
            "post": post,
            "recommended_category": recommended_category,
            "recommended_subcategory": recommended_subcategory,
            "recommended_items": recommended_items,
            "related_links": related_links,
            "related_products": recommended_items,
        }
    )
    context["structured_data_graph"].append(article_node(post))

    return render(request, "main/pages/blog/detail.html", context)
