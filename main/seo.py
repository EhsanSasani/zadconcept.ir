"""Canonical URL and structured-data helpers for public pages."""

from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone


PAGINATED_ROUTE_NAMES = {
    "bakery",
    "gifts",
    "flowers_all",
    "bakery_all",
    "gifts_all",
    "flower_subcategory",
    "bakery_subcategory",
    "gift_subcategory",
    "flower_occasion",
    "occasion_detail",
}


def is_public_pagination(request):
    match = getattr(request, "resolver_match", None)
    return bool(match and match.url_name in PAGINATED_ROUTE_NAMES)


def site_url():
    return settings.ZAD_SITE_URL.rstrip("/")


def absolute_site_url(path_or_url="/"):
    value = str(path_or_url or "/")
    parts = urlsplit(value)
    if parts.scheme and parts.netloc:
        return value
    if not value.startswith("/"):
        value = f"/{value}"
    return f"{site_url()}{value}"


def canonical_url(request):
    """Return a canonical URL that never depends on the incoming Host header."""
    url = absolute_site_url(request.path)
    query_keys = set(request.GET)
    page = request.GET.get("page")

    if (
        is_public_pagination(request)
        and query_keys == {"page"}
        and page
        and page.isdigit()
        and int(page) > 1
    ):
        return f"{url}?page={int(page)}"

    return url


def robots_content(request):
    """Index real pages and pagination, but not filters or partial endpoints."""
    query_keys = set(request.GET)
    if not query_keys:
        return "index,follow"

    if is_public_pagination(request) and query_keys == {"page"}:
        page = request.GET.get("page", "")
        if page.isdigit() and int(page) >= 1:
            return "index,follow"

    return "noindex,follow"


def social_image_url(image=None):
    if image:
        try:
            image = image.url
        except AttributeError:
            pass
        return absolute_site_url(image)
    return settings.ZAD_DEFAULT_SOCIAL_IMAGE


def social_image_dimensions(image=None):
    """Return trustworthy image dimensions without failing on remote/missing files."""
    if image:
        try:
            width = int(image.width)
            height = int(image.height)
            if width > 0 and height > 0:
                return width, height
        except (AttributeError, FileNotFoundError, OSError, TypeError, ValueError):
            pass
    return settings.ZAD_DEFAULT_SOCIAL_IMAGE_WIDTH, settings.ZAD_DEFAULT_SOCIAL_IMAGE_HEIGHT


def business_id():
    return f"{site_url()}/#business"


def website_id():
    return f"{site_url()}/#website"


def business_and_website_nodes():
    address = {
        "@type": "PostalAddress",
        "streetAddress": settings.ZAD_ADDRESS_STREET,
        "addressLocality": settings.ZAD_ADDRESS_LOCALITY,
        "addressRegion": settings.ZAD_ADDRESS_REGION,
        "addressCountry": settings.ZAD_ADDRESS_COUNTRY,
    }
    if settings.ZAD_ADDRESS_POSTAL_CODE:
        address["postalCode"] = settings.ZAD_ADDRESS_POSTAL_CODE

    business = {
        "@type": ["Organization", "Florist"],
        "@id": business_id(),
        "name": "ZAD Flower & Concept Store",
        "alternateName": "زاد",
        "url": site_url(),
        "logo": {
            "@type": "ImageObject",
            "url": settings.ZAD_LOGO_URL,
            "width": settings.ZAD_LOGO_WIDTH,
            "height": settings.ZAD_LOGO_HEIGHT,
        },
        "image": settings.ZAD_DEFAULT_SOCIAL_IMAGE,
        "telephone": settings.ZAD_PHONE_E164,
        "address": address,
        "areaServed": {
            "@type": "City",
            "name": settings.ZAD_ADDRESS_LOCALITY,
        },
        "sameAs": [settings.ZAD_INSTAGRAM_URL, settings.ZAD_TELEGRAM_URL],
        "contactPoint": {
            "@type": "ContactPoint",
            "telephone": settings.ZAD_PHONE_E164,
            "contactType": "customer service",
            "availableLanguage": ["fa", "en"],
            "areaServed": "IR",
        },
        "openingHoursSpecification": [
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": [
                    "Saturday",
                    "Sunday",
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                ],
                "opens": "10:00",
                "closes": "22:00",
            }
        ],
    }
    if settings.ZAD_EMAIL:
        business["email"] = settings.ZAD_EMAIL

    website = {
        "@type": "WebSite",
        "@id": website_id(),
        "url": site_url(),
        "name": "ZAD Flower & Concept Store",
        "inLanguage": ["fa-IR", "en"],
        "publisher": {"@id": business_id()},
    }
    return [business, website]


def page_node(
    canonical,
    title,
    description,
    schema_type="WebPage",
    language="fa-IR",
):
    return {
        "@type": schema_type,
        "@id": f"{canonical}#webpage",
        "url": canonical,
        "name": title,
        "description": description,
        "inLanguage": language,
        "isPartOf": {"@id": website_id()},
        "about": {"@id": business_id()},
    }


def base_graph(
    canonical,
    title,
    description,
    schema_type="WebPage",
    language="fa-IR",
):
    return [
        *business_and_website_nodes(),
        page_node(
            canonical,
            title,
            description,
            schema_type=schema_type,
            language=language,
        ),
    ]


def breadcrumbs_node(breadcrumbs, current_path):
    items = []
    for position, crumb in enumerate(breadcrumbs, start=1):
        crumb_url = crumb.get("url") or current_path
        items.append(
            {
                "@type": "ListItem",
                "position": position,
                "name": crumb["name"],
                "item": absolute_site_url(crumb_url),
            }
        )
    return {
        "@type": "BreadcrumbList",
        "@id": f"{absolute_site_url(current_path)}#breadcrumb",
        "itemListElement": items,
    }


def faq_node(faq_items, canonical, language="fa-IR"):
    return {
        "@type": "FAQPage",
        "@id": f"{canonical}#faq",
        "inLanguage": language,
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
            }
            for item in faq_items
        ],
    }


def product_node(product):
    canonical = absolute_site_url(product.get_absolute_url())
    node = {
        "@type": "Product",
        "@id": f"{canonical}#product",
        "url": canonical,
        "name": product.seo_name,
        "description": product.seo_description,
        "sku": product.product_code,
        "category": product.category.name,
        "brand": {"@type": "Brand", "name": "ZAD"},
    }

    images = []
    if product.cover_image:
        images.append(absolute_site_url(product.cover_image.url))
    for gallery_image in product.gallery_images.all():
        if gallery_image.image:
            images.append(absolute_site_url(gallery_image.image.url))
    if images:
        node["image"] = images

    if product.has_price:
        node["offers"] = {
            "@type": "Offer",
            "url": canonical,
            "price": str(int(product.price) * 10),
            "priceCurrency": "IRR",
            "availability": product.schema_availability,
            "itemCondition": "https://schema.org/NewCondition",
            "seller": {"@id": business_id()},
        }

    return node


def service_node(canonical):
    return {
        "@type": "Service",
        "@id": f"{canonical}#service",
        "url": canonical,
        "name": "ارسال همان‌روز گل در مشهد",
        "serviceType": "Same-day flower delivery",
        "description": "هماهنگی سفارش گل‌های آماده و ارسال همان‌روز در شهر مشهد.",
        "provider": {"@id": business_id()},
        "areaServed": {
            "@type": "City",
            "name": settings.ZAD_ADDRESS_LOCALITY,
        },
    }


def event_node(event):
    canonical = absolute_site_url(event.get_absolute_url())
    node = {
        "@type": "Event",
        "@id": f"{canonical}#event",
        "url": canonical,
        "name": event.title,
        "description": event.description,
        "startDate": event.start_at.isoformat(),
        "endDate": event.end_at.isoformat(),
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": (
            "https://schema.org/EventCompleted"
            if event.end_at < timezone.now()
            else "https://schema.org/EventScheduled"
        ),
        "location": {
            "@type": "Place",
            "name": "ZAD",
            "address": event.location,
        },
        "organizer": {"@id": business_id()},
    }
    if event.cover_image:
        node["image"] = [absolute_site_url(event.cover_image.url)]
    return node


def article_node(post):
    canonical = absolute_site_url(post.get_absolute_url())
    node = {
        "@type": "Article",
        "@id": f"{canonical}#article",
        "url": canonical,
        "headline": post.title,
        "description": post.excerpt or post.body[:160],
        "inLanguage": "fa-IR",
        "author": {"@id": business_id()},
        "publisher": {"@id": business_id()},
        "dateModified": post.updated_at.isoformat(),
        "mainEntityOfPage": {"@id": f"{canonical}#webpage"},
    }
    if post.published_at:
        node["datePublished"] = post.published_at.isoformat()
    if post.cover_image:
        node["image"] = [absolute_site_url(post.cover_image.url)]
    return node
