"""Shared publication boundaries and safe, curated editorial presentation."""
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import NewsPost, Product, PublishStatus, validate_editorial_url


def public_posts(queryset=None):
    queryset = NewsPost.objects.all() if queryset is None else queryset
    return queryset.filter(status=PublishStatus.PUBLISHED).filter(
        Q(published_at__isnull=True) | Q(published_at__lte=timezone.now())
    )


def safe_editorial_url(value):
    try:
        validate_editorial_url(value)
    except (ValidationError, ValueError):
        return ""
    return value


def article_context(post):
    blocks, toc = [], []
    for block in post.blocks.all():
        anchor = f"section-{block.pk}"
        table = block.table_data
        valid_table = isinstance(table, list) and table and all(isinstance(row, list) for row in table)
        item = {key: getattr(block, key) for key in (
            "kind", "title", "body", "image", "alt_text", "caption", "link_label"
        )}
        item.update(anchor=anchor, headers=table[0] if valid_table else [],
                    rows=table[1:] if valid_table else [], link_url=safe_editorial_url(block.link_url) if block.link_url else "")
        blocks.append(item)
        if block.kind == "heading":
            toc.append({"id": anchor, "title": block.title})
    connections = []
    for connection in post.product_connections.filter(
        product__in=Product.objects.publicly_indexable()
    ).select_related("product", "product__category").prefetch_related("product__tags"):
        product = connection.product
        if product.stock_status == Product.StockStatus.OUT_OF_STOCK:
            label = "ناموجود؛ برای جایگزین هماهنگ کنید"
        elif product.is_same_day:
            label = "ارسال روز؛ تأیید موجودی و زمان لازم است"
        else:
            label = "سفارشی؛ هماهنگی زمان و هزینه"
        connections.append({"product": product, "reason": connection.reason, "availability_label": label})
    links = [{"label": link.label, "url": link.url, "description": link.description}
             for link in post.editorial_links.all() if safe_editorial_url(link.url)]
    return {"article_blocks": blocks, "toc": toc, "recommended_connections": connections,
            "related_posts": public_posts(post.related_articles.all()).exclude(pk=post.pk),
            "related_links": links}
