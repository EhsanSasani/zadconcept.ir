from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.cache import patch_cache_control, patch_vary_headers

from ..editorial import article_context, public_posts
from ..models import NewsPost
from ..page_context import _default_context, _with_home
from ..seo import article_node


def blog(request):
    topic = request.GET.get("topic", "")
    if topic not in dict(NewsPost.Topic.choices):
        topic = ""
    queryset = public_posts().order_by("-published_at", "-created_at", "-pk")
    if topic:
        queryset = queryset.filter(topic=topic)
    paginator = Paginator(queryset, 9)
    page = paginator.get_page(request.GET.get("page"))
    context = _default_context(
        request, page_type="category", active_nav="",
        meta_title="مجله زاد | راهنمای گل، هدیه و مناسبت‌ها",
        meta_description="راهنمای انتخاب و سفارش گل در مشهد، مقایسه چیدمان‌ها و مراقبت از گل؛ برای تصمیم‌گیری قبل از سفارش.",
        breadcrumbs=_with_home([{"name": "مجله زاد", "url": None}]),
        content_page="blog", suppress_default_hero=True,
    )
    context.update(posts=page.object_list, page_obj=page, paginator=paginator,
                   current_topic=topic, selected_topic=topic,
                   topics=[{"value": value, "label": label, "url": reverse("blog") + "?" + urlencode({"topic": value})}
                           for value, label in NewsPost.Topic.choices])
    return render(request, "main/pages/blog/index.html", context)


def blog_detail(request, slug):
    user = getattr(request, "user", None)
    is_preview = bool(request.GET.get("preview") == "1" and user and user.is_active and user.is_staff and user.has_perm("main.change_newspost"))
    queryset = NewsPost.objects.all() if is_preview else public_posts()
    post = get_object_or_404(queryset.select_related("primary_category").prefetch_related("blocks", "editorial_links"), slug=slug)
    context = _default_context(
        request, page_type="category", active_nav="",
        meta_title=post.seo_title or f"{post.title} | مجله زاد",
        meta_description=post.meta_description or post.excerpt or "راهنمای انتخاب و سفارش گل از مجله زاد.",
        breadcrumbs=_with_home([{"name": "مجله زاد", "url": reverse("blog")}, {"name": post.title, "url": None}]),
        enable_product_modal=True, content_page="blog-detail", suppress_default_hero=True,
        og_type="article", social_image=post.cover_image if post.cover_image else None,
        is_indexable=not is_preview,
    )
    context.update(article_context(post))
    products = [connection["product"] for connection in context["recommended_connections"]]
    context.update(post=post, is_preview=is_preview, recommended_items=products, related_products=products)
    if not is_preview:
        context["structured_data_graph"].append(article_node(post))
    response = render(request, "main/pages/blog/detail.html", context)
    # A cache must not share an editor's preview with an anonymous visitor.
    patch_vary_headers(response, ["Cookie"])
    if is_preview:
        response["X-Robots-Tag"] = "noindex, nofollow"
        patch_cache_control(response, private=True, no_store=True, max_age=0)
    return response
