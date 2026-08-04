"""Catalog HTTP views.

Extracted from the historical view module; shared presentation policy remains in
``main.views.legacy`` until its dedicated lower layer is complete.
"""

from .support import (
    CATALOG_PAGE_SIZE,
    CATEGORY_SLUG_ALIASES,
    COLLECTION_LANDING_CONTENT,
    Category,
    FLOWER_FILTER_ORDER,
    Http404,
    JsonResponse,
    LeadRequestForm,
    OCCASION_CARD_CONTENT,
    Product,
    SAME_DAY_TAG_SLUG,
    SECTION_CONTENT,
    Tag,
    _catalog_ordered_products,
    _category_card,
    _category_content,
    _default_context,
    _filter_links_for_categories,
    _get_site_hero,
    _hero_from_key,
    _occasion_detail_hero,
    _paginate_products,
    _published_products,
    _published_products_for_section,
    _section_all_url,
    _section_category_url,
    _with_home,
    get_object_or_404,
    redirect,
    render,
    render_to_string,
    reverse,
    service_node,
)

def _collection_landing_page(
    request,
    section,
    *,
    excluded_category_slugs=(),
    directory_only=False,
):
    config = SECTION_CONTENT[section]
    landing = COLLECTION_LANDING_CONTENT[section]

    products_qs = _published_products_for_section(section)
    categories_qs = Category.objects.filter(section=section, is_active=True)
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
            "partials/product_card.html",
            {
                "products": products,
                "card_variant": "landing",
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
                "page_count": len(products),
                "total_count": page_obj.paginator.count,
            }
        )
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Cache-Control"] = "no-store"
        return response

    categories = list(categories_qs.distinct().order_by("sort_order", "name"))
    if section == Category.Section.FLOWERS:
        order = {slug: index for index, slug in enumerate(FLOWER_FILTER_ORDER)}
        categories.sort(key=lambda category: order.get(category.slug, len(order)))

    filter_categories = [
        {
            "name": category.name,
            "slug": category.slug,
            "url": _section_category_url(category),
        }
        for category in categories
    ]
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
            "catalog_filter_categories": filter_categories,
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

    return render(request, "flowers_landing.html", context)

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

def _section_all_products(request, section):
    config = SECTION_CONTENT[section]
    products_qs = _published_products_for_section(section).order_by(
        "-featured",
        "sort_order",
        "-created_at",
    )

    categories = list(
        Category.objects.filter(
            section=section,
            is_active=True,
            children__isnull=True,
        ).order_by("sort_order", "name")
    )

    selected_category = None
    selected_slug = request.GET.get("category") or ""

    if selected_slug:
        selected_category = get_object_or_404(
            Category,
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

    return render(request, "subcategory.html", context)

def flowers_same_day(request):
    products = (
        Product.objects.filter(
            category__section=Category.Section.FLOWERS,
            is_active=True,
            publish_status=Product.PublishStatus.PUBLISHED,
            tags__slug=SAME_DAY_TAG_SLUG,
        )
        .select_related("category")
        .prefetch_related("tags")
        .distinct()
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

    return render(request, "subcategory.html", context)

def flowers_all(request):
    return _section_all_products(request, Category.Section.FLOWERS)

def bakery_all(request):
    return _section_all_products(request, Category.Section.BAKERY)

def gifts_all(request):
    return _section_all_products(request, Category.Section.GIFTS)

def _section_subcategory(request, section, subcategory_slug):
    category = get_object_or_404(
        Category,
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
    items = list(
        _published_products()
        .filter(category_id__in=visible_category_ids)
        .select_related("category")
        .prefetch_related("tags")
        .order_by("-featured", "sort_order", "-created_at")[:48]
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
            "child_categories": [
                _category_card(child) for child in child_categories
            ],
            "lead_form": LeadRequestForm(initial_lead_type=config["lead_type"]),
            "lead_default_type": config["lead_type"],
        }
    )

    return render(request, "subcategory.html", context)

def flower_subcategory(request, subcategory_slug):
    canonical_slug = CATEGORY_SLUG_ALIASES.get(subcategory_slug, subcategory_slug)

    if canonical_slug != subcategory_slug:
        return redirect("flower_subcategory", subcategory_slug=canonical_slug)

    return _section_subcategory(request, Category.Section.FLOWERS, canonical_slug)

def bakery_subcategory(request, subcategory_slug):
    return _section_subcategory(request, Category.Section.BAKERY, subcategory_slug)

def gift_subcategory(request, subcategory_slug):
    return _section_subcategory(request, Category.Section.GIFTS, subcategory_slug)

def flower_occasion(request, slug):
    if slug == "wedding":
        return redirect("flower_subcategory", subcategory_slug="wedding", permanent=True)

    occasion = get_object_or_404(
        Tag,
        slug=slug,
        is_occasion=True,
        is_active=True,
    )

    card = OCCASION_CARD_CONTENT.get(occasion.slug, {})

    base_products_qs = (
        _published_products_for_section(Category.Section.FLOWERS)
        .filter(tags=occasion)
        .order_by("-featured", "sort_order", "-created_at")
    )

    available_category_ids = list(
        base_products_qs.values_list("category_id", flat=True).distinct()
    )

    available_categories = list(
        Category.objects.filter(
            pk__in=available_category_ids,
            is_active=True,
        ).order_by("sort_order", "name")
    )

    selected_slug = request.GET.get("category") or ""
    selected_category = None
    products_qs = base_products_qs

    if selected_slug:
        selected_category = get_object_or_404(
            Category,
            section=Category.Section.FLOWERS,
            slug=selected_slug,
            is_active=True,
            pk__in=available_category_ids,
        )
        products_qs = products_qs.filter(category=selected_category)

    products = list(products_qs[:48])
    suggested_sections = []

    for suggestion_section, title in (
        (Category.Section.BAKERY, "Matching Bakery"),
        (Category.Section.GIFTS, "Complementary Gifts"),
    ):
        section_products = list(
            _published_products_for_section(suggestion_section)
            .filter(tags=occasion)
            .order_by("-featured", "sort_order", "-created_at")[:6]
        )

        if section_products:
            suggested_sections.append(
                {
                    "title": title,
                    "products": section_products,
                    "more_url": reverse("occasion_detail", args=[occasion.slug]),
                }
            )

    title = card.get("hero_title") or f"{occasion.name} Flowers"

    if selected_category:
        title = f"{selected_category.name} / {card.get('title') or occasion.name}"

    breadcrumbs = _with_home(
        [
            {"name": "Flowers", "url": reverse("flowers")},
            {"name": occasion.name, "url": None},
        ]
    )

    context = _default_context(
        request,
        page_type="flower-occasion",
        active_nav="flowers",
        meta_title=f"{title} | سفارش در مشهد از زاد",
        meta_description=f"مشاهده انتخاب‌های {title} و هماهنگی سریع سفارش و ارسال در مشهد از زاد.",
        breadcrumbs=breadcrumbs,
        enable_product_modal=True,
        content_page="occasion-detail",
    )

    hero_data = _occasion_detail_hero(occasion, title=title)

    db_hero = _get_site_hero("occasions", occasion.slug, allow_fallback=False)

    if db_hero:
        hero_data.update(db_hero)

    context.update(hero_data)

    base_url = reverse("flower_occasion", args=[occasion.slug])

    context.update(
        {
            "occasion": occasion,
            "products": products,
            "filter_links": _filter_links_for_categories(
                base_url,
                available_categories,
                selected_slug=selected_slug,
            ),
            "selected_category": selected_category,
            "suggested_sections": suggested_sections,
            "global_occasion_url": reverse("occasion_detail", args=[occasion.slug]),
            "is_flower_occasion": True,
        }
    )

    return render(request, "occasion_detail.html", context)
