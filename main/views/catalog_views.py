from ..seo import service_node
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Case, IntegerField, Value, When
from django.http import Http404, JsonResponse
from django.template.loader import render_to_string

from ..category_presentation import _category_card
from ..catalog_selectors import _published_products, _published_same_day_products
from ..models import (
    BAKERY_WEDDING_CATEGORY_SLUGS,
    FLOWER_PROTECTED_WEDDING_CATEGORY_SLUGS,
    UNIQUE_TAG_SLUG,
    WEDDING_LEGACY_TAG_SLUGS,
)
from ..page_presentation import _category_content

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ..category_presentation import _section_category_url
from ..catalog_selectors import _published_products_for_section
from ..forms import LeadRequestForm
from ..managed_heroes import _get_site_hero
from ..models import Category
from ..page_context import _default_context, _with_home
from ..page_presentation import SECTION_CONTENT, _hero_from_key


SECTION_ALL_ROUTE_NAMES = {
    Category.Section.FLOWERS: "flowers_all",
    Category.Section.BAKERY: "bakery_all",
    Category.Section.GIFTS: "gifts_all",
}

def _section_all_url(section):
    route_name = SECTION_ALL_ROUTE_NAMES.get(section)

    if route_name:
        return reverse(route_name)

    return reverse(section)

def _filter_links_for_categories(
    base_url,
    categories,
    selected_slug=None,
    *,
    selected_section=None,
    include_section=False,
):
    links = [
        {
            "label": "همه",
            "slug": "all",
            "section": "",
            "filter_value": "all",
            "url": base_url,
            "is_active": not selected_slug,
        }
    ]

    for category in categories:
        filter_url = f"{base_url}?category={category.slug}"

        if include_section:
            filter_url += f"&section={category.section}"

        links.append(
            {
                "label": category.name,
                "slug": category.slug,
                "section": category.section,
                "filter_value": category.slug,
                "url": _section_category_url(category),
                "filter_url": filter_url,
                "is_active": (
                    selected_slug == category.slug
                    and (not include_section or selected_section == category.section)
                ),
            }
        )

    return links


def _unique_filter_links(base_url, *, selected_tag=""):
    return [
        {
            "label": "همه",
            "slug": "all",
            "section": "",
            "filter_value": "all",
            "url": base_url,
            "is_active": not selected_tag,
        },
        {
            "label": "یونیک",
            "slug": UNIQUE_TAG_SLUG,
            "section": "",
            "filter_value": UNIQUE_TAG_SLUG,
            "url": f"{base_url}?tag={UNIQUE_TAG_SLUG}",
            "is_active": selected_tag == UNIQUE_TAG_SLUG,
        },
    ]

def _section_all_products(request, section):
    config = SECTION_CONTENT[section]
    products_qs = _published_products_for_section(section).order_by(
        "-featured",
        "sort_order",
        "-created_at",
    )

    categories = list(
        Category.objects.for_general_catalog().filter(
            section=section,
            is_active=True,
            children__isnull=True,
        ).order_by("sort_order", "name")
    )

    selected_category = None
    selected_slug = request.GET.get("category") or ""

    if selected_slug:
        selected_category = get_object_or_404(
            Category.objects.for_general_catalog(),
            section=section,
            slug=selected_slug,
            is_active=True,
        )
        if selected_category.children.filter(is_active=True).exists():
            return redirect(selected_category.get_absolute_url(), permanent=True)
        products_qs = products_qs.filter(category=selected_category)

    items = list(products_qs[:48])
    title = config["title"]

    if selected_category:
        title = f"{config['title']} / {selected_category.name}"

    breadcrumbs = _with_home(
        [
            {"name": config["title"], "url": reverse(section)},
            {"name": "All Products", "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="subcategory",
        active_nav=config["nav"],
        meta_title=f"{title} در مشهد | زاد",
        meta_description=f"مشاهده و سفارش محصولات بخش {config['title']} زاد با هماهنگی ارسال در مشهد.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="subcategory",
    )

    hero_data = _hero_from_key(
        section,
        title=title,
        text="همه محصولات فعال این بخش را یک‌جا ببینید و برای موجودی و ارسال هماهنگ کنید.",
    )

    db_hero = _get_site_hero(section)

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
            "collection_title": title,
            "collection_intro": config["intro"],
            "items": items,
            "filter_links": _filter_links_for_categories(
                _section_all_url(section),
                categories,
                selected_slug=selected_slug,
            ),
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "main/pages/catalog/subcategory.html", context)

def flowers_all(request):
    return _section_all_products(request, Category.Section.FLOWERS)

def bakery_all(request):
    return _section_all_products(request, Category.Section.BAKERY)

def gifts_all(request):
    return _section_all_products(request, Category.Section.GIFTS)

CATEGORY_SLUG_ALIASES = {
    "plant": "plants",
    "wreath": "stand",
    "wedding-decoration": "wedding",
}

WEDDING_FLOWER_LEGACY_SLUGS = frozenset(
    (
        *FLOWER_PROTECTED_WEDDING_CATEGORY_SLUGS,
        *WEDDING_LEGACY_TAG_SLUGS,
    )
)

WEDDING_BAKERY_LEGACY_SLUGS = frozenset(
    (*BAKERY_WEDDING_CATEGORY_SLUGS, *WEDDING_LEGACY_TAG_SLUGS)
)

def _section_subcategory(request, section, subcategory_slug):
    category = get_object_or_404(
        Category.objects.for_general_catalog(),
        section=section,
        slug=subcategory_slug,
        is_active=True,
    )

    config = SECTION_CONTENT[section]
    content = _category_content(category)
    child_categories = list(
        category.children.filter(is_active=True).order_by("sort_order", "name")
    )

    visible_category_ids = [category.pk, *[child.pk for child in child_categories]]
    selected_tag = (request.GET.get("tag") or "").strip()
    if selected_tag not in {"", UNIQUE_TAG_SLUG}:
        raise Http404("Unknown catalog tag filter")

    products_qs = (
        _published_products()
        .filter(category_id__in=visible_category_ids)
        .select_related("category")
        .prefetch_related("tags")
    )
    unique_products_qs = products_qs.filter(
        tags__slug=UNIQUE_TAG_SLUG,
        tags__is_active=True,
    ).distinct()
    has_unique_products = unique_products_qs.exists()

    if selected_tag == UNIQUE_TAG_SLUG:
        products_qs = unique_products_qs

    items = list(
        products_qs.order_by("-featured", "sort_order", "-created_at")[:48]
    )

    breadcrumb_items = [{"name": config["title"], "url": reverse(section)}]
    if category.parent_id:
        breadcrumb_items.append(
            {"name": category.parent.name, "url": category.parent.get_absolute_url()}
        )
    breadcrumb_items.append({"name": category.name, "url": None})
    breadcrumbs = _with_home(breadcrumb_items)
    is_flower_category_page = section == Category.Section.FLOWERS
    db_hero = _get_site_hero("subcategory", category.slug)

    context = _default_context(
        request,
        page_type="subcategory",
        active_nav=config["nav"],
        meta_title=content["meta_title"],
        meta_description=content["meta_description"],
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="subcategory",
        suppress_default_hero=is_flower_category_page and not db_hero,
    )

    hero_data = _hero_from_key(
        "subcategory",
        title=content["label"],
        text=content["intro"],
        image=category.cover_image.url if category.cover_image else content["hero_image"],
    )

    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    category_url = category.get_absolute_url()
    context.update(
        {
            "subcategory_slug": category.slug,
            "subcategory_label": category.name,
            "collection_title": category.name,
            "collection_intro": content["intro"],
            "is_flower_category_page": is_flower_category_page,
            "show_category_split_hero": is_flower_category_page and not db_hero,
            "category_hero_image": (
                category.cover_image.url if category.cover_image else content["image"]
            ),
            "category_parent_label": (
                category.parent.name if category.parent_id else ""
            ),
            "items": items,
            "selected_product_tag": selected_tag,
            "unique_filter_links": (
                _unique_filter_links(category_url, selected_tag=selected_tag)
                if has_unique_products or selected_tag == UNIQUE_TAG_SLUG
                else []
            ),
            "product_empty_text": (
                "فعلاً محصول یونیکی در این دسته وجود ندارد."
                if selected_tag == UNIQUE_TAG_SLUG
                else "فعلاً محصولی برای نمایش وجود ندارد."
            ),
            "child_categories": [
                _category_card(child) for child in child_categories
            ],
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "main/pages/catalog/subcategory.html", context)

def flower_subcategory(request, subcategory_slug):
    if subcategory_slug in WEDDING_FLOWER_LEGACY_SLUGS:
        return redirect("weddings", permanent=True)

    canonical_slug = CATEGORY_SLUG_ALIASES.get(subcategory_slug, subcategory_slug)

    if canonical_slug != subcategory_slug:
        return redirect("flower_subcategory", subcategory_slug=canonical_slug)

    return _section_subcategory(request, Category.Section.FLOWERS, canonical_slug)

def bakery_subcategory(request, subcategory_slug):
    if subcategory_slug in WEDDING_BAKERY_LEGACY_SLUGS:
        return redirect("weddings", permanent=True)

    return _section_subcategory(request, Category.Section.BAKERY, subcategory_slug)

def gift_subcategory(request, subcategory_slug):
    return _section_subcategory(request, Category.Section.GIFTS, subcategory_slug)


COLLECTION_LANDING_CONTENT = {
    Category.Section.FLOWERS: {
        "hero_eyebrow": "FLOWER COLLECTION",
        "hero_title": "استودیو گل زاد",
        "hero_text": "گل‌هایی برای تمام لحظه‌های خاص زندگی شما",
        "hero_image": "main/img/flowers-hero.webp",
        "fallback_image": "main/img/cat-flowers.webp",
        "empty_text": "هنوز محصولی برای نمایش ثبت نشده است.",
        "why_items": [
            {
                "icon": "bi bi-flower1",
                "title": "گل‌های تازه",
                "text": "انتخاب روزانه و چیدمان با دقت",
            },
            {
                "icon": "bi bi-gift",
                "title": "بسته‌بندی شیک",
                "text": "هماهنگ با حس و مناسبت سفارش",
            },
            {
                "icon": "bi bi-truck",
                "title": "ارسال در مشهد",
                "text": "هماهنگی سریع برای تحویل مطمئن",
            },
        ],
        "cta_kicker": "CUSTOM ORDER",
        "cta_title": "دسته‌گل اختصاصی، دقیقاً مطابق سلیقه شما",
        "cta_text": "برای انتخاب رنگ، سبک چیدمان، بودجه و زمان ارسال، با ما تماس بگیرید یا در تلگرام پیام بدهید.",
        "cta_image": "main/img/footer-floral.webp",
        "cta_alt": "سفارش اختصاصی گل",
    },
    Category.Section.BAKERY: {
        "hero_eyebrow": "ZAD SWEET BAR",
        "hero_title": "سوییت بار زاد",
        "hero_text": "طعم‌های شیرین برای لحظه‌های گرم و به‌یادماندنی",
        "hero_image": "main/img/hero-bakery.webp",
        "fallback_image": "main/img/cat-bakery.webp",
        "empty_text": "هنوز محصولی در سوییت بار ثبت نشده است.",
        "why_items": [
            {
                "icon": "bi bi-stars",
                "title": "تازه و خوش‌طعم",
                "text": "آماده‌سازی با مواد اولیه باکیفیت",
            },
            {
                "icon": "bi bi-gift",
                "title": "بسته‌بندی شیک",
                "text": "مناسب هدیه و پذیرایی‌های خاص",
            },
            {
                "icon": "bi bi-truck",
                "title": "ارسال در مشهد",
                "text": "هماهنگی سریع برای تحویل مطمئن",
            },
        ],
        "cta_kicker": "CUSTOM ORDER",
        "cta_title": "سفارش شیرینی اختصاصی، دقیقاً برای مناسبت شما",
        "cta_text": "برای انتخاب طعم، تعداد، نوع بسته‌بندی و زمان ارسال، با ما تماس بگیرید یا در تلگرام پیام بدهید.",
        "cta_image": "main/img/hero-bakery.webp",
        "cta_alt": "سفارش اختصاصی سوییت بار",
    },
    Category.Section.GIFTS: {
        "hero_eyebrow": "ZAD CONCEPT STORE",
        "hero_title": "کانسپت استور زاد",
        "hero_text": "هدیه‌هایی خاص برای آدم‌ها و لحظه‌های خاص زندگی شما",
        "hero_image": "main/img/hero-gifts-v2.webp",
        "fallback_image": "main/img/cat-gifts.webp",
        "empty_text": "هنوز محصولی در کانسپت استور ثبت نشده است.",
        "why_items": [
            {
                "icon": "bi bi-stars",
                "title": "انتخاب‌های خاص",
                "text": "محصولاتی مینیمال و انتخاب‌شده با دقت",
            },
            {
                "icon": "bi bi-gift",
                "title": "بسته‌بندی هدیه",
                "text": "هماهنگ با حس و مناسبت سفارش",
            },
            {
                "icon": "bi bi-truck",
                "title": "ارسال در مشهد",
                "text": "هماهنگی سریع برای تحویل مطمئن",
            },
        ],
        "cta_kicker": "CUSTOM GIFT",
        "cta_title": "هدیه‌ای خاص، دقیقاً مطابق سلیقه شما",
        "cta_text": "برای انتخاب هدیه، بسته‌بندی، بودجه و زمان ارسال، با ما تماس بگیرید یا در تلگرام پیام بدهید.",
        "cta_image": "main/img/gifts-custom-v1.webp",
        "cta_alt": "سفارش هدیه اختصاصی",
    },
}

CATALOG_PAGE_SIZE = 12

FLOWER_FILTER_ORDER = [
    "hand-bouquet",
    "box",
    "bouquet",
    "jarl",
    "stand",
    "plants",
]

def _catalog_ordered_products(queryset, section):
    if section == Category.Section.FLOWERS:
        order = {slug: index for index, slug in enumerate(FLOWER_FILTER_ORDER)}
        cases = [
            When(category__slug=slug, then=Value(index))
            for slug, index in order.items()
        ]
        queryset = queryset.annotate(
            category_rank=Case(
                *cases,
                default=Value(len(order)),
                output_field=IntegerField(),
            )
        )
        return queryset.order_by(
            "category_rank",
            "-featured",
            "sort_order",
            "-created_at",
            "id",
        )

    return queryset.order_by("-featured", "sort_order", "-created_at", "id")

def _paginate_products(request, queryset):
    paginator = Paginator(queryset, CATALOG_PAGE_SIZE)
    page_number = request.GET.get("page") or 1

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        raise Http404("Catalog page does not exist")

    return page_obj

def _collection_landing_page(
    request,
    section,
    *,
    excluded_category_slugs=(),
    directory_only=False,
):
    config = SECTION_CONTENT[section]
    landing = COLLECTION_LANDING_CONTENT[section]
    page = request.GET.get("page")

    if (
        directory_only
        and set(request.GET) == {"page"}
        and page
        and page.isdigit()
        and int(page) >= 1
    ):
        return redirect(reverse(section), permanent=True)
    products_qs = _published_products_for_section(section)
    categories_qs = Category.objects.for_general_catalog().filter(
        section=section,
        is_active=True,
    )
    if directory_only:
        categories_qs = categories_qs.filter(parent__isnull=True)

    if excluded_category_slugs:
        products_qs = products_qs.exclude(category__slug__in=excluded_category_slugs)
        categories_qs = categories_qs.exclude(slug__in=excluded_category_slugs)

    selected_category_slug = request.GET.get("category") or ""
    selected_category = None

    if selected_category_slug and directory_only:
        selected_category = get_object_or_404(
            categories_qs,
            slug=selected_category_slug,
        )
        return redirect(selected_category.get_absolute_url(), permanent=True)

    if selected_category_slug:
        selected_category = get_object_or_404(
            categories_qs,
            slug=selected_category_slug,
        )
        products_qs = products_qs.filter(category=selected_category)

    if directory_only:
        page_obj = None
        products = []
    else:
        products_qs = _catalog_ordered_products(products_qs, section)
        page_obj = _paginate_products(request, products_qs)
        products = list(page_obj.object_list)

    if request.GET.get("partial") == "products":
        if directory_only:
            raise Http404("The flowers landing page is a category directory")
        html = render_to_string(
            "main/components/product_card.html",
            {
                "products": products,
                "fallback_image": landing["fallback_image"],
                "empty_text": landing["empty_text"],
            },
            request=request,
        )

        response = JsonResponse(
            {
                "html": html,
                "has_next": page_obj.has_next(),
                "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
            }
        )
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Cache-Control"] = "no-store"
        return response

    categories = list(categories_qs.distinct().order_by("sort_order", "name"))
    if section == Category.Section.FLOWERS:
        order = {slug: index for index, slug in enumerate(FLOWER_FILTER_ORDER)}
        categories.sort(key=lambda category: order.get(category.slug, len(order)))

    catalog_filter_items = _filter_links_for_categories(
        reverse(section),
        categories,
        selected_slug=selected_category.slug if selected_category else None,
    )
    landing_category_cards = [_category_card(category) for category in categories]

    context = _default_context(
        request,
        page_type="flowers_landing",
        active_nav=config["nav"],
        meta_title=config["meta_title"],
        meta_description=config["meta_description"],
        breadcrumbs=None,
        enable_product_modal=not directory_only,
        content_page=section,
    )
    page_hero = _get_site_hero(section)
    context.update(page_hero or _hero_from_key(section))
    context.update(
        {
            "section": section,
            "catalog_products": products,
            "catalog_page_obj": page_obj,
            "catalog_filter_items": catalog_filter_items,
            "landing_category_cards": landing_category_cards,
            "directory_only": directory_only,
            "selected_category_slug": selected_category.slug if selected_category else "",
            "catalog_page_size": CATALOG_PAGE_SIZE,
            "catalog_load_url": reverse(section),
            "landing_hero_eyebrow": (
                page_hero["page_hero_kicker"]
                if page_hero
                else landing["hero_eyebrow"]
            ),
            "landing_hero_title": (
                page_hero["page_hero_title"]
                if page_hero
                else landing["hero_title"]
            ),
            "landing_hero_text": (
                page_hero["page_hero_text"]
                if page_hero
                else landing["hero_text"]
            ),
            "landing_hero_image": (
                page_hero["page_hero_image"]
                if page_hero
                else landing["hero_image"]
            ),
            "landing_hero_mobile_image": (
                page_hero["page_hero_mobile_image"] if page_hero else ""
            ),
            "landing_fallback_image": landing["fallback_image"],
            "landing_empty_text": landing["empty_text"],
            "landing_why_items": landing["why_items"],
            "landing_cta_kicker": landing["cta_kicker"],
            "landing_cta_title": landing["cta_title"],
            "landing_cta_text": landing["cta_text"],
            "landing_cta_image": landing["cta_image"],
            "landing_cta_alt": landing["cta_alt"],
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "main/pages/catalog/landing.html", context)

def flowers(request):
    return _collection_landing_page(
        request,
        Category.Section.FLOWERS,
        directory_only=True,
    )

def bakery(request):
    return _collection_landing_page(request, Category.Section.BAKERY)

def gifts(request):
    return _collection_landing_page(request, Category.Section.GIFTS)


def flowers_same_day(request):
    products = (
        _published_same_day_products()
        .select_related("category")
        .prefetch_related("tags")
        .order_by("sort_order", "-updated_at")
    )

    breadcrumbs = _with_home(
        [
            {"name": "گل‌ها", "url": reverse("flowers")},
            {"name": "ارسال امروز", "url": None},
        ]
    )
    context = _default_context(
        request,
        page_type="catalog",
        active_nav="flowers",
        meta_title="ارسال گل امروز در مشهد | زاد",
        meta_description=(
            "سفارش گل‌های آماده برای ارسال همان‌روز در مشهد؛ "
            "بررسی موجودی و هماهنگی سریع با زاد."
        ),
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="subcategory",
        schema_type="CollectionPage",
    )
    hero_data = {
        "page_hero_title": "ارسال امروز",
        "page_hero_text": "گل‌های آماده برای ارسال سریع در شهر مشهد.",
        "page_hero_image": "main/img/hero-about.webp",
    }
    db_hero = _get_site_hero("subcategory", "same-day")
    if db_hero:
        hero_data = db_hero

    context.update(hero_data)
    context.update(
        {
        "collection_title": "گل‌هایی برای همین امروز",
        "collection_kicker": "SAME DAY SELECTION",
        "collection_intro": (
            "منتخب‌هایی که آماده‌اند تا با هماهنگی سریع، "
            "همین امروز در مشهد به دست شما برسند."
        ),
        "subcategory_label": "ارسال امروز",
        "items": products,
        "is_same_day_page": True,
        }
    )
    context["structured_data_graph"].append(service_node(context["canonical_url"]))

    return render(request, "main/pages/catalog/subcategory.html", context)
