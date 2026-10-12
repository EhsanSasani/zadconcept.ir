"""Deterministic, availability-aware complements across ZAD's shop sections."""

from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.urls import reverse

from .models import Category, Product


SECTION_LABELS = {
    Category.Section.FLOWERS: "گل برای همراهی این هدیه",
    Category.Section.BAKERY: "یک همراه شیرین از سوییت‌بار",
    Category.Section.GIFTS: "انتخابی از کانسپت‌استور",
}


def complementary_groups(product, limit=4):
    """Rank each complementary section independently so one cannot crowd out another.

    Ready stock wins over preorder, then shared active occasion tags, editorial
    featuring and catalog order. Prices in different currencies are not compared.
    """
    section = product.category.section
    if section not in SECTION_LABELS:
        return []
    occasion_ids = list(product.tags.filter(is_active=True, is_occasion=True).values_list("pk", flat=True))
    eligible = Product.objects.published().filter(
        Q(pk__in=Product.objects.for_general_catalog().values("pk"))
        | Q(pk__in=Product.objects.for_same_day().values("pk"))
    ).exclude(pk=product.pk).exclude(stock_status=Product.StockStatus.OUT_OF_STOCK)
    eligible = eligible.filter(Q(category__parent__isnull=True) | Q(category__parent__is_active=True))
    groups = []
    for target, title in SECTION_LABELS.items():
        if target == section:
            continue
        products = list(eligible.filter(category__section=target).annotate(
            stock_priority=Case(When(stock_status=Product.StockStatus.IN_STOCK, then=Value(0)), default=Value(1), output_field=IntegerField()),
            occasion_matches=Count("tags", filter=Q(tags__pk__in=occasion_ids), distinct=True),
        ).select_related("category").prefetch_related("tags").order_by(
            "stock_priority", "-occasion_matches", "-featured", "sort_order", "-created_at", "pk"
        )[:limit])
        if products:
            groups.append({"section": target, "title": title, "url": reverse(target), "products": products,
                           "reason": "با اولویت موجودی و مناسبت مشترک" if any(item.occasion_matches for item in products) else "برای کامل‌تر شدن هدیهٔ شما"})
    return groups
