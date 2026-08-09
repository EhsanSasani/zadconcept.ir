"""Blog HTTP views."""

from .support import (
    NewsPost,
    PublishStatus,
    _default_context,
    _get_site_hero,
    _hero_from_key,
    _with_home,
    article_node,
    get_object_or_404,
    render,
    reverse,
)

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

    return render(request, "blog_list.html", context)

def blog_detail(request, slug):
    post = get_object_or_404(
        NewsPost,
        slug=slug,
        status=PublishStatus.PUBLISHED,
    )

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

    context["post"] = post
    context["structured_data_graph"].append(article_node(post))

    return render(request, "blog_detail.html", context)
