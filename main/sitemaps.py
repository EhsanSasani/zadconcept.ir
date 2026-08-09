from types import SimpleNamespace
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone

from .models import Category, Event, NewsPost, PublishStatus
from .selectors.catalog import (
    catalog_categories,
    catalog_occasion_tags,
    published_products,
)


class CanonicalSitemap(Sitemap):
    """Force sitemap locations to use the one configured production origin."""

    def get_urls(self, page=1, site=None, protocol=None):
        origin = urlsplit(settings.ZAD_SITE_URL)
        canonical_site = SimpleNamespace(domain=origin.netloc)
        return super().get_urls(
            page=page,
            site=canonical_site,
            protocol=origin.scheme,
        )


class StaticViewSitemap(CanonicalSitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return [
            "index",
            "flowers",
            "flowers_all",
            "bakery",
            "bakery_all",
            "gifts",
            "gifts_all",
            "occasions",
            "flowers_same_day",
            "events",
            "blog",
            "about",
            "contact",
            "faq",
            "privacy",
            "terms",
            "delivery_policy",
            "refund_policy",
            "payment_methods",
            "service_area",
            "international_orders",
            "international_orders_en",
            "mashhad_hub",
            "mashhad_flower_order",
            "mashhad_flower_delivery",
        ]

    def location(self, item):
        return reverse(item)


class CategorySitemap(CanonicalSitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return (
            catalog_categories().filter(
                section__in=(
                    Category.Section.FLOWERS,
                    Category.Section.BAKERY,
                    Category.Section.GIFTS,
                ),
            )
            .order_by("section", "sort_order", "name")
        )

    def lastmod(self, obj):
        return obj.updated_at


class OccasionSitemap(CanonicalSitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return (
            catalog_occasion_tags()
        )

    def lastmod(self, obj):
        return obj.updated_at


class ProductSitemap(CanonicalSitemap):
    changefreq = "daily"
    priority = 0.9

    def items(self):
        return (
            published_products()
            .select_related("category")
            .order_by("-updated_at")
        )

    def lastmod(self, obj):
        return obj.updated_at


class EventSitemap(CanonicalSitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Event.objects.filter(
            status=PublishStatus.PUBLISHED,
            end_at__gte=timezone.now(),
        ).order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


class BlogSitemap(CanonicalSitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return NewsPost.objects.filter(status=PublishStatus.PUBLISHED).order_by(
            "-updated_at"
        )

    def lastmod(self, obj):
        return obj.updated_at


sitemaps = {
    "static": StaticViewSitemap,
    "categories": CategorySitemap,
    "occasions": OccasionSitemap,
    "products": ProductSitemap,
    "events": EventSitemap,
    "blog": BlogSitemap,
}
